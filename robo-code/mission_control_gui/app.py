from nicegui import ui
import requests
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:42000/api/v1"
PORT = 42002

# Enable dark mode
ui.dark_mode(True)

####################################################################################################
#               STATE
####################################################################################################

pending_commands = []
executed_commands = []
is_frozen = True
total_commands_sent = 0
auto_refresh_timer = None
auto_refresh_active = True

####################################################################################################
#               FUNCTIONS
####################################################################################################

def send_command():
    """Send command to backend"""
    global total_commands_sent
    try:
        device_id = device_select.value
        action = action_select.value
        x_val = float(x_input.value or 0)
        y_val = float(y_input.value or 0)
        z_val = float(z_input.value or 0)

        payload = {
            "device_id": device_id,
            "action": action,
            "params": {"x": x_val, "y": y_val, "z": z_val}
        }

        response = requests.post(f"{BACKEND_URL}/commands", json=payload, timeout=5)
        response.raise_for_status()
        result = response.json()

        total_commands_sent = result.get("command_count", total_commands_sent)
        update_commands_sent_label()

        status_label.set_text(f"✓ Command sent: {result['command_id']} (#{result.get('command_count', '?')})")
        refresh_pending()
        refresh_executed()
        clear_form()
        logger.info(f"Command sent: {device_id} → {action}")
    except Exception as e:
        status_label.set_text(f"✗ Error: {str(e)}")
        logger.error(f"Error sending command: {e}")

def refresh_pending():
    """Refresh pending commands from backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/commands/pending", timeout=5)
        response.raise_for_status()
        pending_commands.clear()
        pending_commands.extend(response.json())
        update_pending_table()
    except Exception as e:
        logger.error(f"Error fetching pending commands: {e}")

def refresh_executed():
    """Refresh executed commands from backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/commands/executed", timeout=5)
        response.raise_for_status()
        executed_commands.clear()
        executed_commands.extend(response.json())
        update_executed_table()
    except Exception as e:
        logger.error(f"Error fetching executed commands: {e}")

def clear_form():
    """Clear form inputs"""
    x_input.set_value("")
    y_input.set_value("")
    z_input.set_value("")

def update_commands_sent_label():
    """Update the commands sent counter at the top"""
    commands_sent_label.set_text(f"Total Commands Sent: {total_commands_sent}")

def update_pending_table():
    """Update pending commands table (exclude executed commands)"""
    executed_ids = {cmd.get("command_id") for cmd in executed_commands}
    rows = []
    for cmd in pending_commands:
        # Only show if not yet executed
        if cmd.get("command_id") not in executed_ids:
            rows.append({
                "ID": cmd.get("command_id", ""),
                "Device": cmd.get("device_id", ""),
                "Action": cmd.get("action", ""),
                "X": cmd.get("params", {}).get("x", ""),
                "Y": cmd.get("params", {}).get("y", ""),
                "Z": cmd.get("params", {}).get("z", "")
            })
    pending_table.rows = rows
    # Update count
    pending_count_label.set_text(f"📊 Total Pending: {len(rows)}")

def update_executed_table():
    """Update executed commands table (newest first)"""
    rows = []
    for cmd in executed_commands:
        rows.append({
            "seq": cmd.get("seq_num", "?"),
            "id": cmd.get("command_id", ""),
            "device": cmd.get("device_id", ""),
            "action": cmd.get("action", ""),
            "x": cmd.get("params", {}).get("x", ""),
            "y": cmd.get("params", {}).get("y", ""),
            "z": cmd.get("params", {}).get("z", "")
        })
    # Reverse to show newest first
    executed_table.rows = list(reversed(rows))
    # Update count
    executed_count_label.set_text(f"📊 Total Sent: {len(rows)}")
    # Also update pending table to remove executed commands
    update_pending_table()

def toggle_auto_refresh():
    """Toggle auto-refresh on/off"""
    global auto_refresh_active, auto_refresh_timer
    auto_refresh_active = not auto_refresh_active

    if auto_refresh_active:
        auto_refresh_timer = ui.timer(1, refresh_executed)
        auto_refresh_button.set_text("⏸ Pause Auto-Refresh")
        auto_refresh_label.set_text("Auto-refresh: ON")
    else:
        if auto_refresh_timer:
            auto_refresh_timer.active = False
        auto_refresh_button.set_text("▶ Resume Auto-Refresh")
        auto_refresh_label.set_text("Auto-refresh: OFF")

def check_freeze_state():
    """Check backend freeze state"""
    global is_frozen
    try:
        response = requests.get(f"{BACKEND_URL}/state", timeout=5)
        response.raise_for_status()
        is_frozen = response.json()["is_frozen"]
        update_freeze_button()
    except Exception as e:
        logger.error(f"Error checking freeze state: {e}")

def unfreeze_system():
    """Unfreeze the system"""
    global is_frozen
    try:
        response = requests.post(f"{BACKEND_URL}/unfreeze", timeout=5)
        response.raise_for_status()
        is_frozen = False
        update_freeze_button()
        status_label.set_text("✓ System unfrozen")
        logger.info("System unfrozen")
    except Exception as e:
        status_label.set_text(f"✗ Error unfreezing: {str(e)}")
        logger.error(f"Error unfreezing: {e}")

def freeze_system():
    """Freeze the system"""
    global is_frozen
    try:
        response = requests.post(f"{BACKEND_URL}/freeze", timeout=5)
        response.raise_for_status()
        is_frozen = True
        update_freeze_button()
        status_label.set_text("✓ System frozen")
        logger.info("System frozen")
    except Exception as e:
        status_label.set_text(f"✗ Error freezing: {str(e)}")
        logger.error(f"Error freezing: {e}")

def toggle_freeze():
    """Toggle freeze state"""
    if is_frozen:
        unfreeze_system()
    else:
        freeze_system()

def update_freeze_button():
    """Update freeze/unfreeze button display"""
    if is_frozen:
        freeze_button.set_text("🔒 Unfreeze System")
        send_button.props("color=warning")  # Yellow when frozen
    else:
        freeze_button.set_text("▶ Freeze System")
        send_button.props("color=positive")  # Green when unfrozen

####################################################################################################
#               UI LAYOUT
####################################################################################################

# Header
ui.label("Mission Control GUI").style("font-size: 28px; font-weight: bold")



####################################################################################################
#               3-COLUMN LAYOUT
####################################################################################################

with ui.row().classes("w-full gap-4"):



    # COLUMN 1: Send Command
    with ui.card().classes("flex-1"):

        # System State
        ui.label("System State").style("font-size: 14px; font-weight: bold")
        with ui.row():
            freeze_button = ui.button("🔒 Unfreeze System", on_click=toggle_freeze).props("color=warning")
            auto_refresh_button = ui.button("⏸ Pause Auto-Refresh", on_click=toggle_auto_refresh).props("color=info")
        auto_refresh_label = ui.label("Auto-refresh: ON").style("font-size: 11px; color: #27ae60; font-weight: bold")

        ui.label("Send Command").style("font-size: 16px; font-weight: bold")
        commands_sent_label = ui.label("Total Commands Sent: 0").style("font-size: 12px; color: #3498db; font-weight: bold")

        with ui.row():
            device_select = ui.select(["sat_1", "sat_2", "sat_3", "sat_4", "sat_5", "sat_6", "sat_7", "sat_8", "sat_9", "sat_10"], value="sat_1", label="Device")
            action_select = ui.select(["thrust"], value="thrust", label="Action")

        ui.label("Parameters").style("font-size: 12px; font-weight: bold")
        with ui.row():
            x_input = ui.input(label="X", value="10.5")
            y_input = ui.input(label="Y", value="20.3")
            z_input = ui.input(label="Z", value="-5.2")

        send_button = ui.button("Send Command", on_click=send_command).props("color=primary").classes("w-full")
        status_label = ui.label("Ready").style("color: #27ae60; font-weight: bold")

    # COLUMN 2: Pending Commands
    with ui.card().classes("flex-1"):
        with ui.row().classes("w-full items-center"):
            ui.label("Pending Commands").style("font-size: 16px; font-weight: bold")
            ui.button("Refresh", on_click=refresh_pending).props("color=secondary")

        ui.label("Waiting for execution").style("font-size: 12px; color: #95a5a6")

        with ui.card().classes("w-full").style("background-color: rgba(52, 152, 219, 0.1); padding: 8px;"):
            pending_count_label = ui.label("📊 Total Pending: 0").style("font-size: 13px; font-weight: bold; color: #3498db")

        pending_table = ui.table(columns=[
            {"name": "ID", "label": "ID", "field": "ID"},
            {"name": "Device", "label": "Device", "field": "Device"},
            {"name": "Action", "label": "Action", "field": "Action"},
            {"name": "X", "label": "X", "field": "X"},
            {"name": "Y", "label": "Y", "field": "Y"},
            {"name": "Z", "label": "Z", "field": "Z"},
        ], rows=[])
        pending_table.classes("w-full")
        pending_table.style("--row-height: 32px;")

    # COLUMN 3: Executed Commands
    with ui.card().classes("flex-1"):
        with ui.row().classes("w-full items-center"):
            ui.label("Sent Commands").style("font-size: 16px; font-weight: bold")
            ui.button("Refresh", on_click=refresh_executed).props("color=secondary")

        ui.label("Execution history").style("font-size: 12px; color: #95a5a6")

        with ui.card().classes("w-full").style("background-color: rgba(46, 204, 113, 0.1); padding: 8px;"):
            executed_count_label = ui.label("📊 Total Sent: 0").style("font-size: 13px; font-weight: bold; color: #2ecc71")

        executed_table = ui.table(columns=[
            {"name": "seq", "label": "Seq", "field": "seq"},
            {"name": "id", "label": "ID", "field": "id"},
            {"name": "device", "label": "Device", "field": "device"},
            {"name": "action", "label": "Action", "field": "action"},
            {"name": "x", "label": "X", "field": "x"},
            {"name": "y", "label": "Y", "field": "y"},
            {"name": "z", "label": "Z", "field": "z"},
        ], rows=[])
        executed_table.classes("w-full")
        executed_table.style("max-height: 300px; overflow-y: auto; --row-height: 32px;")

####################################################################################################
#               STARTUP
####################################################################################################

def startup():
    """Initialize UI on load"""
    global auto_refresh_timer
    check_freeze_state()
    update_freeze_button()
    refresh_pending()
    refresh_executed()
    update_commands_sent_label()
    # Start auto-refresh by default (refresh both pending and executed)
    auto_refresh_timer = ui.timer(1, lambda: [refresh_pending(), refresh_executed()])

startup()

ui.run(host="0.0.0.0", port=PORT)
