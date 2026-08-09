# Domain name
From cloudflare ($11.86/year!!!)
http://cesiumlab.net




# Network Devices
Instead of the topology, this is just a list of the devices in the network. (topology in the [topology](topology.md) doc).

## mr-ray
Inspired by the Nimo Mini PC. Lives at `mr.ray`

### Services
- dnsmasq
- cloudflared
- tailscale

### Scratch


# Ports

| Port Range | Purpose
| ---------- | --------------------------
| 5000-5099  | Ground station services
| 5100-5199  | Flight computer telemetry
| 5200-5299  | GNC simulation
| 5300-5399  | HITL 
| 5400-5499  | Cameras/video
| 5500-5599  | Logging/data archive
| 5600-5699  | Robot control
| 5700-5799  | Sensor streaming
| 5800-5899  | Development/debug
| 5900-5999  | Web dashboards
