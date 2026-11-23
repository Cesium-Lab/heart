#!/usr/bin/env bash
# status.sh: read-only overview of mr-ray (services, APIs, docker, storage).
# Changes nothing and needs no sudo.
#
#   See everything:                ./scripts/status.sh
#   Skip outside services:         ./scripts/status.sh --quick
#   Why is <name> FAILED?          journalctl -u <name> -n 50 --no-pager
#   Stop / start / restart one:    sudo systemctl stop|start|restart <name>
#   Turn one off for good:         sudo systemctl disable --now <name>
#
#   Shows "manual"? Something is running by hand on that port: find it with
#   `ss -ltnp 'sport = :<port>'`, kill it, then install the real unit with
#   ./scripts/deploy-startup.sh. Track a new service by adding a line to SERVICES below.

set -uo pipefail

QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

# unit | port ("-" if none/unknown) | health URL ("-" if none)
SERVICES=(
    "apache2|80|http://127.0.0.1/"
    "cloudflared|-|-"
    "cesium-frontend|42800|-"
    "frontend-build|-|-"
    "setlister|42903|http://127.0.0.1:42903/api/setlister/health"
    "rotation-viz|42902|http://127.0.0.1:42902/api/rotation/health"
    "planes|42901|http://127.0.0.1:42901/api/planes/health"
    "inbox|42904|http://127.0.0.1:42904/inbox/health"
    "dataviz-backend|42000|http://127.0.0.1:42000/api/v1/health"
    "dataviz-gui|42002|http://127.0.0.1:42002/"
    "docker|-|-"
    "mysql|3306|-"
    "smbd|445|-"
    "ssh|22|-"
    "tailscaled|-|-"
)

if [[ -t 1 ]]; then G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' D=$'\e[2m' N=$'\e[0m'; else G='' Y='' R='' D='' N=''; fi

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
    [[ "$type" == "oneshot" && "$state" == "active" ]] && label=$(cell "$G" 10 "done")

    note=""
    if [[ "$url" != "-" && "$state" == "active" ]]; then
        if curl -fsS -m 3 -o /dev/null "$url" 2>/dev/null; then note="${G}ok${N}"; else note="${R}no response${N}"; fi
    elif [[ "$port" != "-" && "$state" == "active" ]] && ! listening "$port"; then
        note="${Y}port not listening${N}"
    fi
    printf '%-18s %s %-6s %s\n' "$unit" "$label" "$port" "$note"
done

# ------------------------------------------------------------------ APIs
# label | URL | optional Host header | optional summary (python expression on JSON `d`)
PUBLIC_APIS=(
    "rotation   /api/rotation/health|http://127.0.0.1/api/rotation/health||"
    "setlister  /api/setlister/health|http://127.0.0.1/api/setlister/health||"
    "dataviz    /api/dataviz/health|http://127.0.0.1/api/dataviz/health||d.get('status','')"
    "planes     /api/planes/health|http://127.0.0.1/api/planes/health||"
    "planes     /api/planes/board|http://127.0.0.1/api/planes/board||f\"{len(d.get('aircraft',[]))} aircraft, data {int(time.time()-d.get('updated',0))}s old\" + (', ' + d['error'] if d.get('error') else '') + (f\", {d['routes_pending']} routes pending\" if d.get('routes_pending') else '')"
    "planes     /api/planes/weather|http://127.0.0.1/api/planes/weather||f\"{d.get('station')} {d.get('category') or '?'}\" + (', ' + d['error'] if d.get('error') else '')"
    "planes     /api/planes/replay|http://127.0.0.1/api/planes/replay||f\"{len(d.get('planes',[]))} planes recorded\""
    "dataviz.cesiumlab.net|http://127.0.0.1/|dataviz.cesiumlab.net|"
)
# Outside services the site depends on (one tiny request each).
UPSTREAM_APIS=(
    "adsb.fi (positions)|https://opendata.adsb.fi/api/v2/hex/000000||"
    "adsbdb (routes)|https://api.adsbdb.com/v0/callsign/UAL1||"
    "aviationweather (METAR)|https://aviationweather.gov/api/data/metar?ids=KSFO&format=json||"
    "OpenFreeMap (map tiles)|https://tiles.openfreemap.org/styles/positron||"
    "unpkg (MapLibre)|https://unpkg.com/maplibre-gl@4.7.1/package.json||"
)

check_api() {
    local label="$1" url="$2" host="$3" summary="$4" out code ms note=""
    local args=(-s -o "$tmp" -w '%{http_code} %{time_total}' -m 8 -A 'cesium-status/1.0')
    [[ -n "$host" ]] && args+=(-H "Host: $host")
    out=$(curl "${args[@]}" "$url" 2>/dev/null) || out="000 0"
    code=${out%% *}
    ms=$(awk -v t="${out##* }" 'BEGIN { printf "%d ms", t * 1000 }')
    if [[ "$code" =~ ^2 ]]; then
        if [[ -n "$summary" ]]; then
            note=$(python3 -c "import json,sys,time; d=json.load(open(sys.argv[1])); print($summary)" "$tmp" 2>/dev/null || echo "unexpected response")
        fi
        printf '  %-34s %s %7s  %s\n' "$label" "$(cell "$G" 4 "$code")" "$ms" "$note"
    else
        [[ "$code" == "000" ]] && code="----"
        printf '  %-34s %s %7s  %s\n' "$label" "$(cell "$R" 4 "$code")" "$ms" "${R}not answering${N}"
    fi
}

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

echo
echo "APIS (public routes, through Apache)"
for row in "${PUBLIC_APIS[@]}"; do
    IFS='|' read -r label url host summary <<<"$row"
    check_api "$label" "$url" "$host" "$summary"
done

echo
if ((QUICK)); then
    echo "UPSTREAM  ${D}(skipped with --quick)${N}"
else
    echo "UPSTREAM (outside services)"
    for row in "${UPSTREAM_APIS[@]}"; do
        IFS='|' read -r label url host summary <<<"$row"
        check_api "$label" "$url" "$host" "$summary"
    done
fi

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
