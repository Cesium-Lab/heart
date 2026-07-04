from fastapi import FastAPI
from fastapi.websockets import WebSocket
from collections import deque
import json
import uvicorn
import time
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from models import TelemetryData, Command, CommandAck

app = FastAPI(title="Mission Control Backend")

PORT = 42000
ADDR = "0.0.0.0"

####################################################################################################
#               STATE
####################################################################################################

# Load example telemetry from JSON
with open("examples/telemetry10.json") as f:
    EXAMPLE_TELEMETRY = json.load(f)

telemetry_store = {t["id"]: t for t in EXAMPLE_TELEMETRY}
command_queue = deque()
executed_commands = []  # List of executed command objects
command_counter = 0
commands_sent = 0
sequence_number = 0
is_frozen = True

####################################################################################################
#               IMPORTS & ROUTES
####################################################################################################



####################################################################################################
#               ASYNC EXECUTION
####################################################################################################

async def execute_command_async(command_id: str, command_data: dict, seq_num: int):
    """Simulate command execution asynchronously (only if not frozen)"""
    try:
        # Wait until system is unfrozen
        while is_frozen:
            await asyncio.sleep(0.1)

        # Simulate 1 second execution
        await asyncio.sleep(1)

        # Only complete if still not frozen
        if not is_frozen:
            # Remove from queue (pending)
            command_queue_list = list(command_queue)
            for cid, cmd in command_queue_list:
                if cid == command_id:
                    command_queue.remove((cid, cmd))
                    # Add to executed with status "done"
                    cmd_copy = cmd.copy()
                    cmd_copy["status"] = "done"
                    executed_commands.append(cmd_copy)
                    break

            logger.info(f"Command {command_id} (seq {seq_num}) execution completed")
        else:
            logger.info(f"Command {command_id} (seq {seq_num}) frozen before completion")

    except Exception as e:
        logger.error(f"Error executing command {command_id}: {e}")

@app.get("/api/v1/status")
def status():
    return int(time.time())

####################################################################################################
#               FREEZE CONTROL
####################################################################################################

@app.get("/api/v1/state")
def get_state():
    """Get current backend state (frozen/unfrozen)"""
    return {
        "is_frozen": is_frozen,
        "timestamp": int(time.time())
    }

@app.post("/api/v1/unfreeze")
def unfreeze():
    """Unfreeze the system - start updating telemetry"""
    global is_frozen
    is_frozen = False
    return {"status": "unfrozen", "timestamp": int(time.time())}

@app.post("/api/v1/freeze")
def freeze():
    """Freeze the system - stop updating telemetry"""
    global is_frozen
    is_frozen = True
    return {"status": "frozen", "timestamp": int(time.time())}

####################################################################################################
#               TELEMETRY
####################################################################################################

@app.post("/api/v1/telemetry")
def post_telemetry(data: TelemetryData):
    """Store telemetry data"""
    telemetry_store[data.id] = data.model_dump()
    return {"status": "ok"}

@app.get("/api/v1/telemetry/latest")
def get_latest_telemetry(id: str = None):
    """Get latest telemetry for all devices or specific device"""
    if id:
        return telemetry_store.get(id, {"error": "Device not found"})
    return telemetry_store

####################################################################################################
#               COMMANDS
####################################################################################################

@app.post("/api/v1/commands")
async def post_command(command: Command):
    """Queue a new command and immediately acknowledge receipt"""
    global command_counter, commands_sent, sequence_number
    command_counter += 1
    commands_sent += 1
    sequence_number = (sequence_number + 1) % 256
    command_id = f"cmd_{command_counter}"

    command_with_id = {
        **command.model_dump(),
        "command_id": command_id,
        "command_count": commands_sent,
        "seq_num": sequence_number,
        "status": "received"
    }
    # Only add to queue (pending) initially
    command_queue.append((command_id, command_with_id))

    # Send immediate ACK
    immediate_ack = {
        "command_id": command_id,
        "seq_num": sequence_number,
        "status": "received",
        "timestamp": int(time.time())
    }

    # Start async execution task
    asyncio.create_task(execute_command_async(command_id, command_with_id, sequence_number))

    return immediate_ack

@app.get("/api/v1/commands/pending")
def get_pending_commands():
    """Get all pending commands in queue"""
    return [cmd[1] for cmd in command_queue]

@app.get("/api/v1/commands/executed")
def get_executed_commands():
    """Get all executed commands with their status"""
    return executed_commands

@app.post("/api/v1/commands/pending/{command_id}/ack")
def ack_command(command_id: str, ack: CommandAck):
    """Acknowledge command execution and remove from queue"""
    # Find and remove the command from queue
    for i, (cid, cmd) in enumerate(list(command_queue)):
        if cid == command_id:
            command_queue.remove((cid, cmd))
            return {
                "status": "ack received",
                "command_id": command_id,
                "command_count": cmd.get("command_count")
            }
    return {"status": "command not found", "command_id": command_id}

####################################################################################################
#               HEALTH
####################################################################################################

@app.get("/api/v1/health")
def health_check():
    """Check backend health and system status"""
    return {
        "status": "ok",
        "backend": "operational",
        "telemetry_devices": len(telemetry_store),
        "pending_commands": len(command_queue),
        "total_commands_sent": commands_sent,
        "timestamp": int(time.time())
    }

####################################################################################################
#               STATS
####################################################################################################

@app.get("/api/v1/stats")
def get_stats():
    """Get telemetry statistics (avg temp, battery, etc.)"""
    if not telemetry_store:
        return {"error": "No telemetry data"}

    # Calculate statistics
    temps = [t["sensors"].get("temp", 0) for t in telemetry_store.values()]
    batteries = [t["sensors"].get("battery", 0) for t in telemetry_store.values()]

    return {
        "total_devices": len(telemetry_store),
        "avg_temperature": round(sum(temps) / len(temps), 2),
        "avg_battery": round(sum(batteries) / len(batteries), 2),
        "min_temperature": min(temps),
        "max_temperature": max(temps),
        "min_battery": min(batteries),
        "max_battery": max(batteries),
        "timestamp": int(time.time())
    }

####################################################################################################
#               WEBSOCKET
####################################################################################################

@app.websocket("/api/v1/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """WebSocket for real-time telemetry streaming"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({
                    "type": "telemetry",
                    "data": telemetry_store,
                    "timestamp": int(time.time())
                })
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host=ADDR, port=PORT)
