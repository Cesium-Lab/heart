#!/usr/bin/env bash
# status.sh: read-only overview of mr-ray (services, ports, docker, storage).
# Changes nothing and needs no sudo.
#
#   See everything:                ./scripts/status.sh
#   Why is <name> FAILED?          journalctl -u <name> -n 50 --no-pager
#   Stop / start / restart one:    sudo systemctl stop|start|restart <name>
#   Turn one off for good:         sudo systemctl disable --now <name>
#
#   Shows "manual"? Something is running by hand on that port: find it with
#   `ss -ltnp 'sport = :<port>'`, kill it, then install the real unit with
#   ./scripts/deploy-startup.sh. Track a new service by adding a line to SERVICES below.

set -uo pipefail

# unit | port ("-" if none/unknown) | health URL ("-" if none)
SERVICES=(
    "apache2|80|http://127.0.0.1/"
    "cloudflared|-|-"
    "cesium-frontend|4321|-"
    "frontend-build|-|-"
    "setlister|5702|http://127.0.0.1:5702/api/setlister/health"
    "rotation-viz|5001|http://127.0.0.1:5001/api/rotation/health"
    "telemetry-viz|5701|http://127.0.0.1:5701/health"
    "planes|5901|http://127.0.0.1:5901/health"
    "dataviz-backend|-|-"
    "dataviz-gui|-|-"
    "docker|-|-"
    "mysql|3306|-"
    "smbd|445|-"
    "ssh|22|-"
    "tailscaled|-|-"
)

if [[ -t 1 ]]; then G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' D=$'\e[2m' N=$'\e[0m'; else G= Y= R= D= N=; fi

# Pad plain text first, then color it, so columns line up with or without color.
cell() { printf '%s%-*s%s' "$1" "$2" "$3" "$N"; }

listening() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }

printf '%-18s %-10s %-6s %s\n' SERVICE STATE PORT HEALTH
for row in "${SERVICES[@]}"; do
    IFS='|' read -r unit port url <<<"$row"
    load=$(systemctl show -p LoadState --value "$unit.service" 2>/dev/null)
    state=$(systemctl is-active "$unit.service" 2>/dev/null)
    type=$(systemctl show -p Type --value "$unit.service" 2>/dev/null)

    if [[ "$load" == "not-found" ]]; then
        # Not installed. Flag anything listening on its port anyway: that's a stray process.
        if [[ "$port" != "-" ]] && listening "$port"; then
            label=$(cell "$Y" 10 manual); note="${Y}running by hand, not a service${N}"
        else
            label=$(cell "$D" 10 absent); note="${D}not installed${N}"
        fi
        printf '%-18s %s %-6s %s\n' "$unit" "$label" "$port" "$note"
        continue
    fi

    case "$state" in
        active)   label=$(cell "$G" 10 active) ;;
        inactive) label=$(cell "$D" 10 stopped) ;;
        failed)   label=$(cell "$R" 10 FAILED) ;;
        *)        label=$(cell "$Y" 10 "$state") ;;
    esac
    [[ "$type" == "oneshot" && "$state" == "active" ]] && label=$(cell "$G" 10 done)

    note=""
    if [[ "$url" != "-" && "$state" == "active" ]]; then
        if curl -fsS -m 3 -o /dev/null "$url" 2>/dev/null; then note="${G}ok${N}"; else note="${R}no response${N}"; fi
    elif [[ "$port" != "-" && "$state" == "active" ]] && ! listening "$port"; then
        note="${Y}port not listening${N}"
    fi
    printf '%-18s %s %-6s %s\n' "$unit" "$label" "$port" "$note"
done

echo
echo "DOCKER"
if command -v docker >/dev/null && docker ps >/dev/null 2>&1; then
    docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | column -t -s $'\t' | sed 's/^/  /'
else
    echo "  ${D}(docker not reachable without sudo)${N}"
fi

echo
echo "STORAGE"
for m in / /srv/state /srv/data; do
    if [[ "$m" == "/" ]] || mountpoint -q "$m" 2>/dev/null; then
        df -h --output=target,size,used,pcent "$m" | tail -1 | awk '{printf "  %-11s %5s used of %5s (%s)\n", $1, $3, $2, $4}'
    else
        echo "  $m  ${R}not mounted${N}"
    fi
done
