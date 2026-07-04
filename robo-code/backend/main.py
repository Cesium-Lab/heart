from fastapi import FastAPI
from fastapi.websockets import WebSocket
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json
import uvicorn

app = FastAPI(title="Mission Control API")

# In-memory state
telemetry_store = {}  # {device_id: telemetry_data}
command_queue = []    # [(command_id, command_data)]
command_counter = 0

PORT = 42000
ADDR = "0.0.0.0"

# Data models
class TelemetryData(BaseModel):
    id: str
    timestamp: int
    sensors: dict
    azimuth: float
    elevation: float

class Command(BaseModel):
    device_id: str
    action: str
    params: dict

class CommandAck(BaseModel):
    status: str  # "executed" or "failed"
    error: Optional[str] = None


####################################################################################################
#               STATUS
####################################################################################################

@app.get("/api/v1/status")
def status():
    import time
    return int(time.time())

####################################################################################################
#               TELEMETRY
####################################################################################################

@app.post("/api/v1/telemetry")
def post_telemetry(data: TelemetryData):
    telemetry_store[data.id] = data.model_dump()
    return {"status": "ok"}

@app.get("/api/v1/telemetry/latest")
def get_latest_telemetry(id: Optional[str] = None):
    if id:
        return telemetry_store.get(id, {"error": "Device not found"})
    return telemetry_store

####################################################################################################
#               COMMAND
####################################################################################################

@app.post("/api/v1/commands")
def post_command(command: Command):
    global command_counter
    command_counter += 1
    command_id = f"cmd_{command_counter}"

    command_with_id = {**command.model_dump(), "command_id": command_id}
    command_queue.append((command_id, command_with_id))

    return {
        "command_id": command_id,
        "status": "queued",
        "queue_position": len(command_queue)
    }

@app.get("/api/v1/commands/pending")
def get_pending_commands():
    return [cmd[1] for cmd in command_queue]

@app.post("/api/v1/commands/pending/{command_id}/ack")
def ack_command(command_id: str, ack: CommandAck):
    global command_queue
    command_queue = [(cid, cmd) for cid, cmd in command_queue if cid != command_id]
    return {"status": "ack received", "command_id": command_id}

####################################################################################################
#               TELEMETRY WEBSOCKET
####################################################################################################

@app.websocket("/api/v1/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Send latest telemetry every time client asks
            data = await websocket.receive_text()
            if data == "ping":
                import time
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
