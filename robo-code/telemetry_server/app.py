from nicegui import ui
import requests
import logging
import time
import numpy as np
from collections import defaultdict
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:42000/api/v1"
HOST = "0.0.0.0"
PORT = 42003
CHART_HEIGHT = 300
REFRESH_INTERVAL = 1.0
WINDOW_SECONDS = 10

# Ring buffer capacity, with a safety margin over the nominal sample count
# (WINDOW_SECONDS / REFRESH_INTERVAL) in case ticks ever bunch up.
CAPACITY = int(WINDOW_SECONDS / REFRESH_INTERVAL * 2)

SENSOR_KEYS = ["temperature", "battery", "pressure", "azimuth", "elevation"]

# Enable dark mode
ui.dark_mode(True)

####################################################################################################
#               STATE
####################################################################################################

def _new_history():
    """Pre-allocated numpy ring buffer per device; unwritten/missing slots are NaN"""
    history = {key: np.full(CAPACITY, np.nan) for key in SENSOR_KEYS}
    history["timestamps"] = np.full(CAPACITY, np.nan)
    history["write_ptr"] = 0
    return history

telemetry_history = defaultdict(_new_history)
total_packets = 0
last_update = None
device_order = None

# Bounds how long we keep sending the (expensive) full-series seed payload
# alongside the cheap append payload. Charts should exist within ~1s of startup;
# once past this, sending the full series every tick would be pure waste.
SEED_ATTEMPT_TICKS = 30
seed_tick_count = 0

# Debug info surfaced in the UI to tell apart backend staleness vs client-side lag
last_debug_info = {}
last_display_latency_ms = 0

####################################################################################################
#               FUNCTIONS
####################################################################################################

def _or_nan(value):
    """A numpy float array can't hold Python None, so missing readings become NaN"""
    return np.nan if value is None else value

def fetch_telemetry():
    """Fetch latest telemetry from backend"""
    global total_packets, last_update, device_order, last_debug_info, last_display_latency_ms
    try:
        fetch_start = time.time()
        response = requests.get(f"{BACKEND_URL}/telemetry/latest", timeout=5)
        response.raise_for_status()
        telemetry_data = response.json()
        fetch_latency_ms = (time.time() - fetch_start) * 1000

        logger.info(f"Fetched telemetry for {len(telemetry_data)} devices")

        if device_order is None:
            device_order = sorted(telemetry_data.keys())

        now = time.time()

        for device_id, telem in telemetry_data.items():
            sensors = telem.get("sensors", {})
            history = telemetry_history[device_id]
            ptr = history["write_ptr"]

            # Overwrite the next ring buffer slot; np.nan when a value is missing
            # (a numpy float array can't hold Python None, unlike the sensors dict)
            history["timestamps"][ptr] = now
            history["temperature"][ptr] = _or_nan(sensors.get("temp"))
            history["battery"][ptr] = _or_nan(sensors.get("battery"))
            history["pressure"][ptr] = _or_nan(sensors.get("pressure"))
            history["azimuth"][ptr] = _or_nan(telem.get("azimuth"))
            history["elevation"][ptr] = _or_nan(telem.get("elevation"))

            history["write_ptr"] = (ptr + 1) % CAPACITY

        total_packets += len(telemetry_data)
        last_update = datetime.now().strftime("%H:%M:%S")

        # Raw packet + freshness check: is the backend's own timestamp for this
        # device close to our local receipt time, or is it actually stale?
        debug_device = device_order[0]
        raw_packet = telemetry_data.get(debug_device, {})
        backend_ts = raw_packet.get("timestamp")
        freshness_ms = (now - backend_ts) * 1000 if backend_ts is not None else None

        last_debug_info = {
            "device": debug_device,
            "packet": raw_packet,
            "fetch_latency_ms": round(fetch_latency_ms, 1),
            "freshness_ms": round(freshness_ms, 1) if freshness_ms is not None else None,
            "prev_display_latency_ms": round(last_display_latency_ms, 1),
        }

        display_start = time.time()
        update_display(now)
        last_display_latency_ms = (time.time() - display_start) * 1000

    except Exception as e:
        logger.error(f"Error fetching telemetry: {e}")

def _valid_window(history, sensor_key, now):
    """Return (times_ms, values) sorted by time, restricted to the last WINDOW_SECONDS
    and excluding NaN (unwritten ring buffer slots or missing sensor readings)"""
    timestamps = history["timestamps"]
    values = history[sensor_key]

    mask = ~np.isnan(timestamps) & ~np.isnan(values) & (timestamps >= now - WINDOW_SECONDS)
    order = np.argsort(timestamps[mask])

    times_ms = (timestamps[mask][order] * 1000)
    return times_ms, values[mask][order]

def calculate_stats(now):
    """Calculate statistics from telemetry history"""
    all_temps = []
    all_batteries = []

    for history in telemetry_history.values():
        _, temps = _valid_window(history, "temperature", now)
        _, batteries = _valid_window(history, "battery", now)
        all_temps.append(temps)
        all_batteries.append(batteries)

    temps = np.concatenate(all_temps) if all_temps else np.array([])
    batteries = np.concatenate(all_batteries) if all_batteries else np.array([])

    avg_temp = round(float(np.mean(temps)), 2) if temps.size else 0
    avg_battery = round(float(np.mean(batteries)), 2) if batteries.size else 0

    return {
        "total_packets": total_packets,
        "avg_temp": avg_temp,
        "avg_battery": avg_battery,
        "active_sats": len(telemetry_history),
        "last_update": last_update or "--:--:--"
    }

def build_series_data(sensor_key, now):
    """Build full windowed series data for ApexCharts (only used to seed a chart once),
    x-axis as unix time in ms"""
    series = []

    for device_id in device_order:
        history = telemetry_history[device_id]
        times_ms, values = _valid_window(history, sensor_key, now)
        series.append({
            "name": device_id,
            "data": [[x, y] for x, y in zip(times_ms.tolist(), values.tolist())]
        })

    return series

def build_latest_points(sensor_key):
    """Just the single newest point per device - O(1) ring buffer read, no scan/mask/sort"""
    appends = []

    for device_id in device_order:
        history = telemetry_history[device_id]
        last_idx = (history["write_ptr"] - 1) % CAPACITY
        t = history["timestamps"][last_idx]
        y = history[sensor_key][last_idx]

        if not np.isnan(t) and not np.isnan(y):
            appends.append({"data": [[float(t * 1000), float(y)]]})
        else:
            appends.append({"data": []})

    return appends

def _init_charts():
    """Initialize ApexCharts instances"""
    init_js = """
    window.chartConfigs = {
        'temp_chart': {title: 'Temperature (°C)', yaxis: 'Temperature'},
        'battery_chart': {title: 'Battery (%)', yaxis: 'Battery'},
        'pressure_chart': {title: 'Pressure (hPa)', yaxis: 'Pressure'},
        'azimuth_chart': {title: 'Azimuth (rad)', yaxis: 'Azimuth'},
        'elevation_chart': {title: 'Elevation (rad)', yaxis: 'Elevation'}
    };

    Object.keys(window.chartConfigs).forEach(chartId => {
        const config = window.chartConfigs[chartId];
        const options = {
            chart: {
                type: 'line',
                id: chartId,
                height: __CHART_HEIGHT__,
                width: '100%',
                toolbar: {show: true},
                animations: {enabled: false}
            },
            title: {text: config.title, style: {fontSize: '14px'}},
            stroke: {curve: 'straight', width: 2},
            grid: {show: true, strokeDashArray: 0},
            xaxis: {
                type: 'datetime',
                title: {text: 'Unix Time'},
                labels: {datetimeUTC: false}
            },
            yaxis: {title: {text: config.yaxis}},
            tooltip: {shared: true, intersect: false},
            legend: {show: true, position: 'top'},
            colors: ['#3498db', '#e74c3c', '#f39c12', '#2ecc71', '#9467bd', '#ff7f0e', '#1f77b4', '#d62728', '#17becf', '#bcbd22']
        };
        window[chartId] = new ApexCharts(document.querySelector('#' + chartId), {
            series: [],
            ...options
        });
        window[chartId].render();
    });
    """.replace("__CHART_HEIGHT__", str(CHART_HEIGHT)).replace("__WINDOW_MS__", str(int(WINDOW_SECONDS * 1000)))
    ui.run_javascript(init_js)

def update_display(now):
    """Update all stats and charts"""
    global seed_tick_count
    stats = calculate_stats(now)

    # Update stats labels
    packets_label.set_text(f"📊 Packets: {stats['total_packets']}")
    temp_label.set_text(f"🌡️ Avg Temp: {stats['avg_temp']}°C")
    battery_label.set_text(f"🔋 Avg Battery: {stats['avg_battery']}%")
    sats_label.set_text(f"🛰️ Active: {stats['active_sats']}")
    update_label.set_text(f"⏱️ {stats['last_update']}")

    # Debug readout: raw packet + timing, to tell apart backend staleness vs client lag
    info = last_debug_info
    debug_label.set_text(
        f"local now:  {now:.3f}\n"
        f"fetch:      {info.get('fetch_latency_ms')} ms\n"
        f"freshness:  {info.get('freshness_ms')} ms (backend ts vs local now)\n"
        f"prev tick:  {info.get('prev_display_latency_ms')} ms (display processing)\n"
        f"device:     {info.get('device')}\n"
        f"packet:\n{json.dumps(info.get('packet', {}), indent=2)}"
    )

    chart_configs = [
        ("temp_chart", "temperature", "Temperature (°C)"),
        ("battery_chart", "battery", "Battery (%)"),
        ("pressure_chart", "pressure", "Pressure (hPa)"),
        ("azimuth_chart", "azimuth", "Azimuth (rad)"),
        ("elevation_chart", "elevation", "Elevation (rad)")
    ]

    # Explicit min/max keeps the axis window locked to "now", since xaxis.range
    # only auto-tracks the latest point via appendData, not plain updateSeries.
    max_ms = int(now * 1000)
    min_ms = int((now - WINDOW_SECONDS) * 1000)

    still_seeding = seed_tick_count < SEED_ATTEMPT_TICKS
    seed_tick_count += 1

    # Build one combined payload for all 5 charts, dispatched as a single
    # run_javascript() call - one websocket message / JS eval instead of five,
    # since each separate call has its own dispatch overhead on the browser side.
    payloads = {}
    for chart_id, sensor_key, title in chart_configs:
        entry = {"appends": build_latest_points(sensor_key)}
        if still_seeding:
            entry["full"] = build_series_data(sensor_key, now)
        payloads[chart_id] = entry

    payloads_json = json.dumps(payloads)

    ui.run_javascript(f"""
    const payloads = {payloads_json};
    Object.keys(payloads).forEach(chartId => {{
        const chart = window[chartId];
        if (!chart) return;
        chart.updateOptions({{ xaxis: {{ min: {min_ms}, max: {max_ms} }} }}, false, false);
        const p = payloads[chartId];
        if (chart.w.globals.series.length === 0 && p.full) {{
            chart.updateSeries(p.full);
        }} else {{
            chart.appendData(p.appends);
        }}
    }});
    """)

####################################################################################################
#               UI LAYOUT
####################################################################################################

# Header
ui.label("Telemetry Dashboard").style("font-size: 28px; font-weight: bold")

# Main 2-column layout
with ui.row().classes("w-full gap-4 flex-nowrap"):

    # LEFT COLUMN: Statistics (1/5 width)
    with ui.card().classes("w-1/5").style("min-width: 0; flex-shrink: 0;"):
        ui.label("Statistics").style("font-size: 16px; font-weight: bold")

        packets_label = ui.label("📊 Packets: 0").style("font-size: 13px; font-weight: bold; color: #3498db")
        temp_label = ui.label("🌡️ Avg Temp: 0°C").style("font-size: 13px; font-weight: bold; color: #e74c3c")
        battery_label = ui.label("🔋 Avg Battery: 0%").style("font-size: 13px; font-weight: bold; color: #f39c12")
        sats_label = ui.label("🛰️ Active: 0").style("font-size: 13px; font-weight: bold; color: #2ecc71")
        update_label = ui.label("⏱️ --:--:--").style("font-size: 12px; color: #95a5a6")

        ui.separator()
        ui.label("Debug").style("font-size: 14px; font-weight: bold")
        debug_label = ui.label("waiting for first packet...").style(
            "font-size: 10px; font-family: monospace; white-space: pre-wrap; color: #bdc3c7;"
        )

    # RIGHT COLUMN: Charts (4/5 width)
    with ui.column().classes("w-4/5").style("min-width: 0;"):
        chart_configs = [
            ("temp_chart", "Temperature (°C)", "#1f77b4"),
            ("battery_chart", "Battery (%)", "#ff7f0e"),
            ("pressure_chart", "Pressure (hPa)", "#2ca02c"),
            ("azimuth_chart", "Azimuth (rad)", "#d62728"),
            ("elevation_chart", "Elevation (rad)", "#9467bd")
        ]

        # One chart per row, full width
        for chart_id, title, _ in chart_configs:
            with ui.row().classes("w-full"):
                ui.html(f'<div id="{chart_id}" style="height: {CHART_HEIGHT}px; width: 95%; margin: 0 auto;"></div>').classes("w-full")

        # Initialize charts on first data fetch
        ui.timer(0.1, lambda: _init_charts(), once=True)

####################################################################################################
#               STARTUP
####################################################################################################

# Load ApexCharts library
ui.add_body_html('<script src="https://cdn.jsdelivr.net/npm/apexcharts@latest"></script>')

logger.info(f"Starting Telemetry Dashboard on {HOST}:{PORT}")

# Start fetching and updating every REFRESH_INTERVAL seconds
ui.timer(REFRESH_INTERVAL, fetch_telemetry)

ui.run(host=HOST, port=PORT)
