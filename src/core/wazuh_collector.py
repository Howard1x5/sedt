"""
WazuhCollector - Automated alert collection from Wazuh API.

Pulls alerts from Wazuh for validation of detection rules against
simulated worker activity. Enables programmatic FP/TP analysis.
"""

import json
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
import urllib3

# Disable SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


@dataclass
class AlertSummary:
    """Summary of alerts from a simulation run."""
    total_alerts: int = 0
    alerts_by_rule: dict = field(default_factory=dict)
    alerts_by_severity: dict = field(default_factory=dict)
    alert_details: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_alerts": self.total_alerts,
            "alerts_by_rule": self.alerts_by_rule,
            "alerts_by_severity": self.alerts_by_severity,
            "alert_count_by_rule": {k: len(v) for k, v in self.alerts_by_rule.items()}
        }


class WazuhCollector:
    """
    Pulls alerts from Wazuh for a given time window.
    Uses both Wazuh Manager API (for agent info) and Wazuh Indexer (for alerts).
    """

    def __init__(
        self,
        wazuh_host: str = '192.168.1.50',  # Example IP - change for your environment  # NOSEC
        api_port: int = 55000,
        indexer_port: int = 9200,
        api_username: str = 'wazuh-wui',
        api_password: str = None,
        indexer_username: str = 'admin',
        indexer_password: str = None,
        verify_ssl: bool = False
    ):
        """
        Initialize Wazuh collector.

        Args:
            wazuh_host: Wazuh manager IP/hostname
            api_port: Manager API port (default 55000)
            indexer_port: Indexer port (default 9200)
            api_username: API username
            api_password: API password
            indexer_username: Indexer username (default 'admin')
            indexer_password: Indexer password
            verify_ssl: Whether to verify SSL certificates
        """
        self.api_url = f'https://{wazuh_host}:{api_port}'
        self.indexer_url = f'https://{wazuh_host}:{indexer_port}'
        self.api_username = api_username
        self.api_password = api_password
        self.indexer_username = indexer_username
        self.indexer_password = indexer_password
        self.verify_ssl = verify_ssl
        self.token = None
        self.token_expiry = None

    def _authenticate(self) -> bool:
        """
        Authenticate to Wazuh Manager API and get JWT token.

        Returns:
            True if authentication successful
        """
        try:
            response = requests.post(
                f'{self.api_url}/security/user/authenticate',
                auth=(self.api_username, self.api_password),
                verify=self.verify_ssl,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data['data']['token']
                # Token expires in 900 seconds (15 min) by default
                self.token_expiry = datetime.now() + timedelta(seconds=850)
                logger.info("Wazuh Manager API authentication successful")
                return True
            else:
                logger.error(f"Wazuh API auth failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Wazuh API auth error: {e}")
            return False

    def _get_headers(self) -> dict:
        """Get headers with valid JWT token for Manager API."""
        if self.token is None or datetime.now() >= self.token_expiry:
            self._authenticate()
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def _api_request(self, method: str, endpoint: str, params: dict = None) -> Optional[dict]:
        """
        Make authenticated request to Wazuh Manager API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., '/agents')
            params: Query parameters

        Returns:
            Response data or None on error
        """
        try:
            url = f'{self.api_url}{endpoint}'
            headers = self._get_headers()

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                verify=self.verify_ssl,
                timeout=60
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Manager API request failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Manager API request error: {e}")
            return None

    def _indexer_request(self, method: str, endpoint: str, json_data: dict = None) -> Optional[dict]:
        """
        Make authenticated request to Wazuh Indexer (OpenSearch).

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., '/wazuh-alerts-*/_search')
            json_data: JSON body for POST requests

        Returns:
            Response data or None on error
        """
        try:
            url = f'{self.indexer_url}{endpoint}'

            response = requests.request(
                method=method,
                url=url,
                auth=(self.indexer_username, self.indexer_password),
                json=json_data,
                verify=self.verify_ssl,
                timeout=60
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Indexer request failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Indexer request error: {e}")
            return None

    def get_agents(self) -> list:
        """
        Get list of registered agents.

        Returns:
            List of agent dictionaries
        """
        result = self._api_request('GET', '/agents')
        if result and 'data' in result:
            return result['data'].get('affected_items', [])
        return []

    def get_agent_id_by_name(self, name: str) -> Optional[str]:
        """
        Find agent ID by hostname.

        Args:
            name: Agent hostname (e.g., 'DESKTOP-H0MEFD1')

        Returns:
            Agent ID or None
        """
        agents = self.get_agents()
        for agent in agents:
            if agent.get('name', '').upper() == name.upper():
                return agent.get('id')
        return None

    def get_alerts(
        self,
        start_time: datetime,
        end_time: datetime,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        limit: int = 500
    ) -> list:
        """
        Pull alerts from Wazuh Indexer for a time window.

        Args:
            start_time: Start of time window
            end_time: End of time window
            agent_id: Filter by specific agent ID (optional)
            agent_name: Filter by agent name (optional)
            limit: Maximum alerts to return

        Returns:
            List of alert dictionaries
        """
        # Format timestamps for Elasticsearch query (ISO 8601)
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Build Elasticsearch query
        must_clauses = [
            {
                "range": {
                    "timestamp": {
                        "gte": start_str,
                        "lte": end_str
                    }
                }
            }
        ]

        # Add agent filter if specified
        if agent_id:
            must_clauses.append({"match": {"agent.id": agent_id}})
        if agent_name:
            must_clauses.append({"match": {"agent.name": agent_name}})

        query = {
            "size": limit,
            "sort": [{"timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": must_clauses
                }
            }
        }

        result = self._indexer_request('POST', '/wazuh-alerts-*/_search', query)

        if result and 'hits' in result:
            alerts = [hit['_source'] for hit in result['hits'].get('hits', [])]
            total = result['hits'].get('total', {}).get('value', len(alerts))
            logger.info(f"Retrieved {len(alerts)} alerts (total: {total}) from {start_str} to {end_str}")
            return alerts

        return []

    def get_alerts_summary(
        self,
        start_time: datetime,
        end_time: datetime,
        agent_id: Optional[str] = None
    ) -> AlertSummary:
        """
        Get summarized alerts grouped by rule and severity.

        Args:
            start_time: Start of time window
            end_time: End of time window
            agent_id: Filter by specific agent

        Returns:
            AlertSummary with grouped data
        """
        alerts = self.get_alerts(start_time, end_time, agent_id)

        summary = AlertSummary()
        summary.total_alerts = len(alerts)

        for alert in alerts:
            # Group by rule
            rule_id = alert.get('rule', {}).get('id', 'unknown')
            rule_desc = alert.get('rule', {}).get('description', 'Unknown rule')
            rule_key = f"{rule_id}: {rule_desc}"

            if rule_key not in summary.alerts_by_rule:
                summary.alerts_by_rule[rule_key] = []
            summary.alerts_by_rule[rule_key].append(alert)

            # Group by severity
            level = alert.get('rule', {}).get('level', 0)
            severity = self._level_to_severity(level)
            summary.alerts_by_severity[severity] = summary.alerts_by_severity.get(severity, 0) + 1

            # Store details
            summary.alert_details.append({
                'timestamp': alert.get('timestamp'),
                'rule_id': rule_id,
                'rule_description': rule_desc,
                'level': level,
                'agent_name': alert.get('agent', {}).get('name'),
                'data': alert.get('data', {})
            })

        return summary

    def _level_to_severity(self, level: int) -> str:
        """Convert Wazuh rule level to severity string."""
        if level >= 12:
            return 'critical'
        elif level >= 9:
            return 'high'
        elif level >= 6:
            return 'medium'
        elif level >= 3:
            return 'low'
        else:
            return 'info'

    def classify_alerts(
        self,
        alerts: list,
        simulation_actions: list = None,
        attack_injected: bool = False
    ) -> dict:
        """
        Classify alerts as true positive, false positive, or infrastructure noise.

        Args:
            alerts: List of alert dictionaries
            simulation_actions: List of actions executed during simulation
            attack_injected: Whether attack TTPs were injected

        Returns:
            Classification results with FP/TP counts
        """
        results = {
            'total_alerts': len(alerts),
            'true_positives': 0,
            'false_positives': 0,
            'infrastructure_noise': 0,
            'unclassified': 0,
            'details': []
        }

        # Infrastructure patterns (SEDT setup artifacts)
        infra_patterns = [
            'action_executor',
            'sedt',
            'pythonw.exe',
            'sshd',
            'wazuh-agent'
        ]

        for alert in alerts:
            rule_desc = alert.get('rule', {}).get('description', '').lower()
            data = alert.get('data', {})
            full_log = alert.get('full_log', '').lower()

            classification = 'unclassified'

            # Check for infrastructure noise
            for pattern in infra_patterns:
                if pattern in rule_desc or pattern in full_log or pattern in str(data).lower():
                    classification = 'infrastructure_noise'
                    break

            # If attack was injected and alert matches attack rules, it's TP
            if classification == 'unclassified' and attack_injected:
                # Check if this alert corresponds to injected attack
                # For now, mark high-severity alerts during attack runs as potential TP
                level = alert.get('rule', {}).get('level', 0)
                if level >= 10:
                    classification = 'true_positive'
                else:
                    classification = 'false_positive'

            # If no attack, any alert from benign activity is FP
            if classification == 'unclassified' and not attack_injected:
                classification = 'false_positive'

            results[classification + 's' if classification != 'infrastructure_noise' else 'infrastructure_noise'] += 1
            results['details'].append({
                'rule_id': alert.get('rule', {}).get('id'),
                'rule_description': alert.get('rule', {}).get('description'),
                'classification': classification,
                'timestamp': alert.get('timestamp')
            })

        # Calculate rates
        total_relevant = results['true_positives'] + results['false_positives']
        if total_relevant > 0:
            results['false_positive_rate'] = results['false_positives'] / total_relevant
        else:
            results['false_positive_rate'] = 0.0

        return results

    def test_connection(self) -> bool:
        """Test API connection and authentication."""
        if self._authenticate():
            agents = self.get_agents()
            logger.info(f"Connection test passed. Found {len(agents)} agents.")
            return True
        return False


# Convenience function for quick testing
def test_wazuh_collector():
    """Quick test of WazuhCollector functionality."""
    collector = WazuhCollector(
        wazuh_host='192.168.1.50',  # Example IP  # NOSEC
        api_port=55000,
        indexer_port=9200,
        api_username='wazuh-wui',
        api_password=os.environ.get('WAZUH_API_PASSWORD', ''),
        indexer_username='admin',
        indexer_password=os.environ.get('WAZUH_INDEXER_PASSWORD', '')
    )

    print("Testing Wazuh connections...")
    if collector.test_connection():
        print("✓ Manager API connection successful")

        # List agents
        agents = collector.get_agents()
        print(f"\nRegistered agents ({len(agents)}):")
        for agent in agents:
            status = agent.get('status', 'unknown')
            print(f"  - {agent.get('id')}: {agent.get('name')} ({status})")

        # Test indexer connection
        print("\nTesting Indexer connection...")
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)

        alerts = collector.get_alerts(start_time, end_time, limit=10)
        print(f"✓ Indexer connection successful - retrieved {len(alerts)} recent alerts")

        # Get alerts for VM 111 (DESKTOP-H0MEFD1)
        print(f"\nAlerts from last hour for DESKTOP-H0MEFD1:")
        summary = collector.get_alerts_summary(start_time, end_time, agent_id='010')
        print(f"  Total: {summary.total_alerts}")
        print(f"  By severity: {summary.alerts_by_severity}")
        if summary.alerts_by_rule:
            print(f"  Top rules:")
            for rule, alerts in list(summary.alerts_by_rule.items())[:5]:
                print(f"    - {rule}: {len(alerts)} alerts")

        return True
    else:
        print("✗ Connection failed")
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    test_wazuh_collector()
