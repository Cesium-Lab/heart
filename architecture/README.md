| Port Range | Purpose                    |
| ---------- | -------------------------- |
| 42000-42099  | Ground station services    |
| 42100-42199  | Flight computer telemetry  |
| 42200-42299  | GNC simulation             |
| 42300-42399  | Hardware-in-the-loop (HITL)|
| 42400-42499  | Cameras/video              |
| 42500-42599  | Logging/data archive       |
| 42600-42699  | Robot control              |
| 42700-42799  | Sensor streaming           |
| 42800-42899  | Development/debug          |
| 42900-42999  | Web dashboards             |

| Port | Service                   |
| ---- | ------------------------- |
| 42000 | T&C Backend       |
| 42001 | (reserved)       |
| 42002 | Mission Control GUI (NiceGUI)       |
| 42003 | Telemetry Server (Grafana)   |
| 42004 | Telemetry Database (Prometheus)   |

 Port | Service                   |
| ---- | ------------------------- |
| 42100 | Flight Computer Telemetry |
| 42101 | Flight Computer Commands  |
| 42200 | 6DOF Simulation           |
| 42201 | Monte Carlo Runs          |
| 42300 | HITL Sensor Feed           |
| 42301 | HITL Actuator Feed         |
| 42600 | Robot State               |
| 42601 | Robot Commands            |
| 42900 | Dashboard                 |
