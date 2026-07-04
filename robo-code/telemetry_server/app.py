from nicegui import ui
import requests
import logging
from collections import defaultdict
from datetime import datetime
import plotly.graph_objects as go
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:42000/api/v1"
HOST = "0.0.0.0"
PORT = 42003

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

        for device_id, telem in telemetry_data.items():
            timestamp = telem.get("timestamp")
            sensors = telem.get("sensors", {})

            # Store in history (keep last 1000 points per device)
            telemetry_history[device_id]["timestamps"].append(timestamp)
            telemetry_history[device_id]["temperature"].append(sensors.get("temp"))
            telemetry_history[device_id]["battery"].append(sensors.get("battery"))
            telemetry_history[device_id]["pressure"].append(sensors.get("pressure"))
            telemetry_history[device_id]["azimuth"].append(telem.get("azimuth"))
            telemetry_history[device_id]["elevation"].append(telem.get("elevation"))

            # Keep only last 1000 points
            for key in telemetry_history[device_id]:
                if len(telemetry_history[device_id][key]) > 1000:
                    telemetry_history[device_id][key] = telemetry_history[device_id][key][-1000:]

        total_packets += len(telemetry_data)
        last_update = datetime.now().strftime("%H:%M:%S")
        update_display()

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

def build_plot_data(sensor_key, sensor_name, sensor_unit):
    """Build trace data for a sensor"""
    traces = []

    for device_id, history in telemetry_history.items():
        if history[sensor_key]:
            # Convert timestamps to relative time (seconds from first)
            first_ts = history["timestamps"][0] if history["timestamps"] else 0
            relative_times = [(t - first_ts) for t in history["timestamps"]]

            traces.append({
                "x": relative_times,
                "y": history[sensor_key],
                "name": device_id
            })

    return traces

def update_display():
    """Update all stats and charts"""
    stats = calculate_stats()

    # Update stats labels
    packets_label.set_text(f"📊 Packets: {stats['total_packets']}")
    temp_label.set_text(f"🌡️ Avg Temp: {stats['avg_temp']}°C")
    battery_label.set_text(f"🔋 Avg Battery: {stats['avg_battery']}%")
    sats_label.set_text(f"🛰️ Active: {stats['active_sats']}")
    update_label.set_text(f"⏱️ {stats['last_update']}")

    # Update plots via JavaScript (no page flicker)
    plot_configs = [
        ("temp_plot", "temperature", "Temperature (°C)"),
        ("battery_plot", "battery", "Battery (%)"),
        ("pressure_plot", "pressure", "Pressure (hPa)"),
        ("azimuth_plot", "azimuth", "Azimuth (rad)"),
        ("elevation_plot", "elevation", "Elevation (rad)")
    ]

    for plot_id, sensor_key, label in plot_configs:
        traces = build_plot_data(sensor_key, "", "")

        # Build JavaScript to update Plotly
        x_data = [t["x"] for t in traces]
        y_data = [t["y"] for t in traces]
        names = [t["name"] for t in traces]

        # Convert lists to JSON strings for embedding in JavaScript
        x_json = json.dumps(x_data)
        y_json = json.dumps(y_data)
        names_json = json.dumps(names)

        js_code = f"""
        const plotDiv = document.getElementById('{plot_id}');
        if (plotDiv) {{
            const xData = {x_json};
            const yData = {y_json};
            const names = {names_json};

            // Initialize if not yet created
            if (!plotDiv.data || plotDiv.data.length === 0) {{
                const traces = [];
                for (let i = 0; i < names.length; i++) {{
                    traces.push({{
                        x: xData[i],
                        y: yData[i],
                        name: names[i],
                        mode: 'lines'
                    }});
                }}
                Plotly.newPlot(plotDiv, traces, {{
                    title: '{label}',
                    xaxis: {{title: 'Time (seconds)'}},
                    yaxis: {{title: '{label}'}},
                    hovermode: 'x unified',
                    margin: {{l: 40, r: 20, t: 40, b: 40}}
                }});
            }} else {{
                // Update existing traces
                if (plotDiv.data.length !== names.length) {{
                    plotDiv.data = [];
                    for (let i = 0; i < names.length; i++) {{
                        plotDiv.data.push({{
                            x: xData[i],
                            y: yData[i],
                            name: names[i],
                            mode: 'lines'
                        }});
                    }}
                }} else {{
                    for (let i = 0; i < names.length; i++) {{
                        plotDiv.data[i].x = xData[i];
                        plotDiv.data[i].y = yData[i];
                    }}
                }}
                Plotly.redraw(plotDiv);
            }}
        }}
        """

        ui.run_javascript(js_code)

####################################################################################################
#               UI LAYOUT
####################################################################################################

# Header
ui.label("Telemetry Dashboard").style("font-size: 28px; font-weight: bold")

# Main 2-column layout
with ui.row().classes("w-full gap-4"):

    # LEFT COLUMN: Statistics (1/5 width)
    with ui.card().classes("w-1/5"):
        ui.label("Statistics").style("font-size: 16px; font-weight: bold")

        packets_label = ui.label("📊 Packets: 0").style("font-size: 13px; font-weight: bold; color: #3498db")
        temp_label = ui.label("🌡️ Avg Temp: 0°C").style("font-size: 13px; font-weight: bold; color: #e74c3c")
        battery_label = ui.label("🔋 Avg Battery: 0%").style("font-size: 13px; font-weight: bold; color: #f39c12")
        sats_label = ui.label("🛰️ Active: 0").style("font-size: 13px; font-weight: bold; color: #2ecc71")
        update_label = ui.label("⏱️ --:--:--").style("font-size: 12px; color: #95a5a6")

    # RIGHT COLUMN: Plots (4/5 width)
    with ui.column().classes("w-4/5"):
        # Create plot divs with explicit IDs
        plot_configs = [
            ("temp_plot", "Temperature", "°C"),
            ("battery_plot", "Battery", "%"),
            ("pressure_plot", "Pressure", "hPa"),
            ("azimuth_plot", "Azimuth", "rad"),
            ("elevation_plot", "Elevation", "rad")
        ]

        with ui.row():
            for plot_id, label, unit in plot_configs[:2]:
                with ui.column().classes("flex-1"):
                    ui.html(f'<div id="{plot_id}" style="height: 300px;"></div>')

        with ui.row():
            for plot_id, label, unit in plot_configs[2:4]:
                with ui.column().classes("flex-1"):
                    ui.html(f'<div id="{plot_id}" style="height: 300px;"></div>')

        with ui.row():
            for plot_id, label, unit in plot_configs[4:]:
                with ui.column().classes("flex-1"):
                    ui.html(f'<div id="{plot_id}" style="height: 300px;"></div>')

####################################################################################################
#               STARTUP
####################################################################################################

logger.info(f"Starting Telemetry Dashboard on {HOST}:{PORT}")

# Start fetching and updating every 0.5 seconds
ui.timer(0.5, fetch_telemetry)

ui.run(host=HOST, port=PORT)
