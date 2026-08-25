# DataViz architecture

DataViz is a proof-of-concept spacecraft command and telemetry stack. It has two
Python services and an optional containerized monitoring pair.

```text
Browser -> NiceGUI dashboard (42002) -> FastAPI backend (42000)
                                             |
                                             +-> /metrics
                                                   |
                                            Prometheus (42004)
                                                   |
                                              Grafana (42003)
```

## Components

| Port  | Component         | Purpose                                                                     |
| ----- | ----------------- | --------------------------------------------------------------------------- |
| 42000 | FastAPI backend   | In-memory telemetry, command queue, simulation, API, and Prometheus metrics |
| 42001 | Reserved          | Available for a future telemetry stream                                     |
| 42002 | NiceGUI dashboard | Command entry, freeze control, and pending/executed command views           |
| 42003 | Grafana           | Provisioned telemetry charts backed by Prometheus                           |
| 42004 | Prometheus        | Scrapes `host.docker.internal:42000/metrics` once per second                |

The backend loads ten simulated satellites from
`backend/examples/telemetry10.json`. When unfrozen, it jitters their telemetry at
10 Hz and executes queued commands after a simulated one-second delay. Freeze
pauses both behaviors. All backend state is process-local and is lost on restart.

Apache exposes the backend under `/api/dataviz/` on the main site and proxies
`dataviz.cesiumlab.net` to NiceGUI. The dashboard talks directly to the loopback
backend, so neither internal Python port needs public exposure.

## Known limitations

- No persistence, authentication, authorization, or command validation beyond the Pydantic request shape.
- No real flight hardware or spacecraft simulator is connected.
- The WebSocket endpoint is request/response (`ping`) rather than a pushed stream.
- Grafana and Prometheus are optional and require Docker Compose.

See [QUICKSTART.md](QUICKSTART.md) for local and production startup instructions.
