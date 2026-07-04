from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import requests
import uvicorn
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Telemetry Dashboard")

PORT = 42003
ADDR = "0.0.0.0"

BACKEND_URL = "http://localhost:42000/api/v1"

####################################################################################################
#               STATUS
####################################################################################################

@app.get("/api/v1/status")
def status():
    """Get telemetry server status"""
    try:
        response = requests.get(f"{BACKEND_URL}/status", timeout=5)
        response.raise_for_status()
        return {
            "status": "ok",
            "backend_timestamp": response.json(),
            "timestamp": int(time.time())
        }
    except Exception as e:
        logger.error(f"Error getting backend status: {e}")
        return {"status": "error", "error": str(e)}

####################################################################################################
#               TELEMETRY
####################################################################################################

@app.get("/api/v1/telemetry/all")
def get_all_telemetry():
    """Get all telemetry data from backend"""
    try:
        response = requests.get(f"{BACKEND_URL}/telemetry/latest", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error getting telemetry: {e}")
        return {}

@app.get("/api/v1/telemetry/{device_id}")
def get_device_telemetry(device_id: str):
    """Get telemetry for specific device"""
    try:
        response = requests.get(f"{BACKEND_URL}/telemetry/latest?id={device_id}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error getting telemetry for {device_id}: {e}")
        return {"error": str(e)}

####################################################################################################
#               STATISTICS
####################################################################################################

@app.get("/api/v1/stats")
def get_stats():
    """Get telemetry statistics (avg temp, battery, etc.)"""
    try:
        response = requests.get(f"{BACKEND_URL}/telemetry/latest", timeout=5)
        response.raise_for_status()
        telemetry = response.json()

        if not telemetry:
            return {"error": "No telemetry data"}

        # Calculate statistics
        temps = [t["sensors"].get("temp", 0) for t in telemetry.values()]
        batteries = [t["sensors"].get("battery", 0) for t in telemetry.values()]

        return {
            "total_devices": len(telemetry),
            "avg_temperature": round(sum(temps) / len(temps), 2),
            "avg_battery": round(sum(batteries) / len(batteries), 2),
            "min_temperature": min(temps),
            "max_temperature": max(temps),
            "min_battery": min(batteries),
            "max_battery": max(batteries),
            "timestamp": int(time.time())
        }
    except Exception as e:
        logger.error(f"Error calculating stats: {e}")
        return {"error": str(e)}

####################################################################################################
#               MONITORING
####################################################################################################

@app.get("/api/v1/health")
def health_check():
    """Check health of telemetry and backend connection"""
    try:
        backend_status = requests.get(f"{BACKEND_URL}/status", timeout=5)
        backend_status.raise_for_status()

        telemetry = requests.get(f"{BACKEND_URL}/telemetry/latest", timeout=5)
        telemetry.raise_for_status()

        return {
            "telemetry_server": "ok",
            "backend": "ok",
            "devices_active": len(telemetry.json()),
            "timestamp": int(time.time())
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "telemetry_server": "ok",
            "backend": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    uvicorn.run(app, host=ADDR, port=PORT)
