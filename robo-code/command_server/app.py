from fastapi import FastAPI
import uvicorn
import asyncio
import logging
from handler import CommandHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Command Server")

PORT = 42001
ADDR = "0.0.0.0"

# Initialize handler
handler = CommandHandler()

# Background task for polling
polling_task = None

@app.on_event("startup")
async def startup():
    """Start polling when server starts"""
    global polling_task
    logger.info("Command Server starting up")
    polling_task = asyncio.create_task(handler.start_polling(interval=2))

@app.on_event("shutdown")
async def shutdown():
    """Cancel polling on shutdown"""
    global polling_task
    if polling_task:
        polling_task.cancel()
    logger.info("Command Server shutting down")

@app.get("/api/v1/status")
def status():
    """Get command server status"""
    return handler.get_status()

@app.get("/api/v1/commands/executed")
def get_executed():
    """Get history of executed commands"""
    return handler.executed_commands

if __name__ == "__main__":
    uvicorn.run(app, host=ADDR, port=PORT)
