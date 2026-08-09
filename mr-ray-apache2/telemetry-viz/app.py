"""
Telemetry Viz Backend
Accepts sensor data via POST, buffers last 100 points per sensor, serves live dashboard.
Run with: python app.py (listens on port 5701)
"""

from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

MAX_POINTS = 100
PORT = 5701

_store: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_POINTS))
_lock = Lock()

app = FastAPI(title="Telemetry Viz", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DASHBOARD_PATH = Path(__file__).parent / "dashboard.html"


class TelemetryPoint(BaseModel):
    timestamp: float
    sensor_name: str
    value: float


def _parse_points(body) -> list[TelemetryPoint]:
    if isinstance(body, dict):
        return [TelemetryPoint.model_validate(body)]
    if isinstance(body, list):
        return [TelemetryPoint.model_validate(item) for item in body]
    raise HTTPException(status_code=400, detail="Expected JSON object or array")


def _store_points(points: list[TelemetryPoint]) -> int:
    with _lock:
        for point in points:
            _store[point.sensor_name].append(
                {"timestamp": point.timestamp, "value": point.value}
            )
    return len(points)


def _read_all() -> dict[str, list[dict]]:
    with _lock:
        return {
            sensor: sorted(list(points), key=lambda p: p["timestamp"])
            for sensor, points in _store.items()
        }


@app.post("/telemetry")
async def post_telemetry(request: Request):
    try:
        body = await request.json()
        points = _parse_points(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    accepted = _store_points(points)
    return {"accepted": accepted}


@app.get("/data")
def get_data():
    return _read_all()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def dashboard():
    if not DASHBOARD_PATH.exists():
        raise HTTPException(status_code=500, detail="dashboard.html not found")
    return FileResponse(DASHBOARD_PATH)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
