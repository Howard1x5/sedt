# SEDT - Simulated Enterprise Detection Testing

An autonomous agent that simulates realistic office worker behavior on Windows endpoints, generating authentic Sysmon and Windows Event logs for detection engineering validation.

## Purpose

Detection rules are only as good as the data they're tested against. SEDT solves the challenge of:

- **False Positive Testing**: Generate realistic benign activity to validate detection rules don't trigger on normal behavior
- **Log Realism**: Produce authentic Windows telemetry that matches real enterprise patterns
- **Scalable Testing**: Simulate multiple worker personas across different roles and behaviors
- **Time Compression**: Run a full simulated workday in minutes for rapid iteration

## Architecture

SEDT uses a split architecture for security and flexibility:

```
┌─────────────────────────────────────┐      ┌─────────────────────────────────────┐
│         Linux Host                  │      │         Windows Endpoint            │
│  ┌─────────────────────────────┐   │      │  ┌─────────────────────────────┐   │
│  │     DecisionEngine          │   │      │  │     ActionExecutor          │   │
│  │  - LLM API integration      │   │ TCP  │  │  - Socket server (:9999)    │   │
│  │  - Worker profile logic     │──────────▶  │  - Executes Windows actions  │   │
│  │  - Contextual decisions     │   │      │  │  - Spawns realistic processes│   │
│  └─────────────────────────────┘   │      │  └─────────────────────────────┘   │
│               │                     │      │               │                    │
│  ┌─────────────────────────────┐   │      │  ┌─────────────────────────────┐   │
│  │     RemoteExecutor          │   │      │  │  Generated Telemetry        │   │
│  │  - Socket communication     │   │      │  │  - Sysmon events            │   │
│  │  - SSH fallback             │   │      │  │  - Windows Security logs    │   │
│  └─────────────────────────────┘   │      │  │  - Process creation (ID 1)  │   │
│                                     │      │  │  - Network conn (ID 3)      │   │
│  ┌─────────────────────────────┐   │      │  │  - File operations (ID 11)  │   │
│  │     Worker Profile          │   │      │  └─────────────────────────────┘   │
│  │  (JSON persona config)      │   │      │               │                    │
│  └─────────────────────────────┘   │      │               ▼                    │
└─────────────────────────────────────┘      │  ┌─────────────────────────────┐   │
                                             │  │     Wazuh Agent             │   │
                                             │  │  (forwards to SIEM)         │   │
                                             │  └─────────────────────────────┘   │
                                             └─────────────────────────────────────┘
```

**Why split architecture?**
- API keys stay on Linux host, never touch Windows endpoint
- Windows VM only receives action commands, no decision logic
- Easier to scale: one decision engine can drive multiple Windows VMs
- Cleaner process trees: ActionExecutor runs at login with explorer.exe parent

## Features

### LLM-Powered Decisions
The DecisionEngine uses an LLM API to make contextual decisions based on:
- Current time of day and work schedule
- Recent action history
- Worker role and typical activities
- Natural task flow patterns

Falls back to weighted heuristics if API unavailable.

### Realistic Action Execution
- **Process creation**: Opens real applications (Edge, Notepad, etc.)
- **Web browsing**: Visits role-appropriate websites
- **File operations**: Creates, copies, moves files in monitored directories
- **Email simulation**: Opens mail client, simulates inbox checks

### Socket-Based Communication
- Persistent connection on port 9999
- 2-18ms execution latency (vs SSH overhead)
- ActionExecutor runs at Windows login for realistic process trees

## Worker Profiles

SEDT uses JSON-based worker personas to drive realistic behavior patterns:

```json
{
  "name": "Alex",
  "role": "Marketing Coordinator",
  "work_schedule": {
    "start_time": "09:00",
    "end_time": "17:00",
    "lunch_break": {"start": "12:00", "duration_minutes": 60},
    "coffee_breaks": ["10:30", "15:00"]
  },
  "applications": {
    "primary": ["outlook", "chrome", "word", "excel", "powerpoint", "teams"]
  },
  "activities": {
    "email": {"frequency": "high", "check_interval_minutes": 15},
    "browser": {
      "typical_sites": ["linkedin.com", "canva.com", "analytics.google.com"]
    },
    "documents": {
      "common_tasks": ["create_presentation", "edit_spreadsheet", "write_copy"]
    }
  }
}
```

## Installation

### Linux Host (Decision Engine)

```bash
# Clone repository
git clone https://github.com/Howard1x5/sedt.git
cd sedt

# Install dependencies
pip install -r requirements.txt

# Configure environment
export ANTHROPIC_API_KEY="your-api-key"
export SEDT_WINDOWS_HOST="192.168.1.100"
export SEDT_WINDOWS_USER="analyst"
export SEDT_WINDOWS_PASSWORD="password"
```

### Windows Endpoint (Action Executor)

1. Install Python 3.10+
2. Copy `src/actions/action_executor.py` to `C:\sedt\`
3. Install Sysmon with SwiftOnSecurity config
4. Run executor at login:
   ```batch
   pythonw.exe C:\sedt\action_executor.py --server --port 9999
   ```

## Usage

```python
from src.core.agent import DetectionSimAgent, SimulationConfig

config = SimulationConfig(
    profile_path="config/profiles/alex_marketing.json",
    time_compression=60.0,  # 1 real second = 1 simulated minute
)

agent = DetectionSimAgent(config)
stats = agent.run()

print(f"Actions executed: {stats.actions_executed}")
print(f"Simulated duration: {stats.simulated_duration}")
```

## Validation

Log output is validated against:

- **OpTC Dataset**: DARPA's enterprise-scale Windows telemetry benchmark
- **SwiftOnSecurity Sysmon Config**: Industry-standard event generation baseline
- **Volume Targets**: 3-10 MB per endpoint per simulated day

## Requirements

**Linux Host:**
- Python 3.10+
- anthropic package (for LLM API)
- SSH access to Windows endpoint

**Windows Endpoint:**
- Windows 10/11
- Python 3.10+
- Sysmon installed
- Wazuh agent (for log forwarding)
- Firewall rule allowing port 9999

## Related Projects

- [detection-as-code](https://github.com/Howard1x5/detection-as-code) - Detection rules tested with SEDT

## License

MIT
