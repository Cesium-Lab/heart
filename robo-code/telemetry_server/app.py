from nicegui import ui
import requests
import logging
import time
from collections import defaultdict
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:42000/api/v1"
HOST = "0.0.0.0"
PORT = 42003
CHART_HEIGHT = 300
REFRESH_INTERVAL = 0.1
WINDOW_SECONDS = 10

# Enable dark mode
ui.dark_mode(True)

####################################################################################################
#               STATE
####################################################################################################

telemetry_history = defaultdict(lambda: {
    "timestamps": [],
    "temperature": [],
    "battery": [],
    "pressure": [],
    "azimuth": [],
    "elevation": []
})
total_packets = 0
last_update = None

####################################################################################################
#               FUNCTIONS
####################################################################################################

def fetch_telemetry():
    """Fetch latest telemetry from backend"""
    global total_packets, last_update
    try:
        response = requests.get(f"{BACKEND_URL}/telemetry/latest", timeout=5)
        response.raise_for_status()
        telemetry_data = response.json()

        logger.info(f"Fetched telemetry for {len(telemetry_data)} devices")

        now = time.time()
        cutoff = now - WINDOW_SECONDS

        for device_id, telem in telemetry_data.items():
            sensors = telem.get("sensors", {})

            # Use local receipt time (sub-second precision) for plotting/windowing
            telemetry_history[device_id]["timestamps"].append(now)
            telemetry_history[device_id]["temperature"].append(sensors.get("temp"))
            telemetry_history[device_id]["battery"].append(sensors.get("battery"))
            telemetry_history[device_id]["pressure"].append(sensors.get("pressure"))
            telemetry_history[device_id]["azimuth"].append(telem.get("azimuth"))
            telemetry_history[device_id]["elevation"].append(telem.get("elevation"))

            # Sliding window: keep only points within the last WINDOW_SECONDS
            timestamps = telemetry_history[device_id]["timestamps"]
            keep_from = next((i for i, t in enumerate(timestamps) if t >= cutoff), len(timestamps))
            if keep_from > 0:
                for key in telemetry_history[device_id]:
                    telemetry_history[device_id][key] = telemetry_history[device_id][key][keep_from:]

        total_packets += len(telemetry_data)
        last_update = datetime.now().strftime("%H:%M:%S")
        update_display(now)

    except Exception as e:
        logger.error(f"Error fetching telemetry: {e}")

def calculate_stats():
    """Calculate statistics from telemetry history"""
    temps = []
    batteries = []

    for device_id, history in telemetry_history.items():
        if history["temperature"]:
            temps.extend([t for t in history["temperature"] if t is not None])
        if history["battery"]:
            batteries.extend([b for b in history["battery"] if b is not None])

    avg_temp = round(sum(temps) / len(temps), 2) if temps else 0
    avg_battery = round(sum(batteries) / len(batteries), 2) if batteries else 0

    return {
        "total_packets": total_packets,
        "avg_temp": avg_temp,
        "avg_battery": avg_battery,
        "active_sats": len(telemetry_history),
        "last_update": last_update or "--:--:--"
    }

def build_series_data(sensor_key):
    """Build series data for ApexCharts, x-axis as unix time in milliseconds"""
    series = []

    for device_id, history in telemetry_history.items():
        if history[sensor_key]:
            # x-axis is absolute unix time in ms (ApexCharts datetime axis)
            unix_times_ms = [t * 1000 for t in history["timestamps"]]

            # Create data points as [x, y] pairs
            data = [[x, y] for x, y in zip(unix_times_ms, history[sensor_key]) if y is not None]

            series.append({
                "name": device_id,
                "data": data
            })

    return series

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
                animations: {enabled: true, speed: 100}
            },
            title: {text: config.title, style: {fontSize: '14px'}},
            stroke: {curve: 'smooth', width: 2},
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
    """.replace("__CHART_HEIGHT__", str(CHART_HEIGHT))
    ui.run_javascript(init_js)

def update_display(now):
    """Update all stats and charts"""
    stats = calculate_stats()

    # Update stats labels
    packets_label.set_text(f"📊 Packets: {stats['total_packets']}")
    temp_label.set_text(f"🌡️ Avg Temp: {stats['avg_temp']}°C")
    battery_label.set_text(f"🔋 Avg Battery: {stats['avg_battery']}%")
    sats_label.set_text(f"🛰️ Active: {stats['active_sats']}")
    update_label.set_text(f"⏱️ {stats['last_update']}")

    # Fixed 10-second window ending at "now", regardless of data present
    max_ms = int(now * 1000)
    min_ms = int((now - WINDOW_SECONDS) * 1000)

    # Update charts via JavaScript
    chart_configs = [
        ("temp_chart", "temperature", "Temperature (°C)"),
        ("battery_chart", "battery", "Battery (%)"),
        ("pressure_chart", "pressure", "Pressure (hPa)"),
        ("azimuth_chart", "azimuth", "Azimuth (rad)"),
        ("elevation_chart", "elevation", "Elevation (rad)")
    ]

    for chart_id, sensor_key, title in chart_configs:
        series = build_series_data(sensor_key)
        series_json = json.dumps(series)

        js_code = f"""
        const chartId = '{chart_id}';
        const series = {series_json};

        if (window[chartId]) {{
            window[chartId].updateOptions({{
                series: series,
                xaxis: {{ type: 'datetime', min: {min_ms}, max: {max_ms} }}
            }}, false, false);
        }}
        """

        ui.run_javascript(js_code)

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
