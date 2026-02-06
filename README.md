# SEDT - Simulated Enterprise Detection Testing

An autonomous agent that simulates realistic office worker behavior on Windows endpoints, generating authentic Sysmon and Windows Event logs for detection engineering validation.

## Purpose

Detection rules are only as good as the data they're tested against. SEDT solves the challenge of:

- **False Positive Testing**: Generate realistic benign activity to validate detection rules don't trigger on normal behavior
- **Log Realism**: Produce authentic Windows telemetry that matches real enterprise patterns
- **Scalable Testing**: Simulate multiple worker personas across different roles and behaviors
- **Time Compression**: Run a full simulated workday in minutes for rapid iteration

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Windows Endpoint                      │
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │  SEDT Agent     │───▶│  Windows Actions            │ │
│  │  (Python)       │    │  - Process creation         │ │
│  │                 │    │  - File operations          │ │
│  │  DecisionEngine │    │  - Network connections      │ │
│  │  ActionExecutor │    │  - Registry access          │ │
│  └─────────────────┘    └─────────────────────────────┘ │
│           │                         │                    │
│           ▼                         ▼                    │
│  ┌─────────────────┐    ┌─────────────────────────────┐ │
│  │  Worker Profile │    │  Sysmon + Windows Events    │ │
│  │  (JSON persona) │    │  (Authentic telemetry)      │ │
│  └─────────────────┘    └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │    Wazuh Server     │
                    │  Detection Rules    │
                    └─────────────────────┘
```

## Worker Profiles

SEDT uses JSON-based worker personas to drive realistic behavior patterns:

```json
{
  "name": "Alex",
  "role": "Marketing Coordinator",
  "work_hours": {"start": "09:00", "end": "17:00"},
  "activities": {
    "email": {"frequency": "high", "apps": ["outlook"]},
    "documents": {"types": ["docx", "xlsx", "pptx"]},
    "browser": {"sites": ["linkedin.com", "canva.com", "analytics.google.com"]}
  },
  "behaviors": {
    "lunch_break": {"start": "12:00", "duration": 60},
    "phone_checks": "frequent"
  }
}
```

## Validation

Log output is validated against:

- **OpTC Dataset**: DARPA's enterprise-scale Windows telemetry benchmark
- **SwiftOnSecurity Sysmon Config**: Industry-standard event generation baseline
- **Volume Targets**: 3-10 MB per endpoint per simulated day

## Requirements

- Windows 10/11 endpoint with Sysmon installed
- Python 3.10+
- Wazuh agent (for log forwarding)

## Related Projects

- [detection-as-code](https://github.com/Howard1x5/detection-as-code) - Detection rules tested with SEDT

## License

MIT
