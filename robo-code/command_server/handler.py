import requests
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

BACKEND_URL = "http://localhost:42000/api/v1"

class CommandHandler:
    def __init__(self):
        self.devices = {}
        self.executed_commands = []

    async def poll_backend(self):
        """Poll backend for pending commands and execute them"""
        try:
            response = requests.get(f"{BACKEND_URL}/commands/pending", timeout=5)
            response.raise_for_status()
            commands = response.json()

            for cmd in commands:
                await self.execute_command(cmd)
        except Exception as e:
            logger.error(f"Error polling backend: {e}")

    async def execute_command(self, command: dict):
        """Execute a command and acknowledge back to backend"""
        command_id = command.get("command_id")
        device_id = command.get("device_id")
        action = command.get("action")
        params = command.get("params", {})

        try:
            # Simulate command execution
            logger.info(f"Executing {action} on {device_id}: {params}")

            # Simulate device operations
            if action == "thrust":
                self._execute_thrust(device_id, params)
            else:
                logger.warning(f"Unknown action: {action}")

            # Acknowledge successful execution
            await self.ack_command(command_id, "executed")
            import time
            self.executed_commands.append({
                "command_id": command_id,
                "timestamp": int(time.time()),
                "status": "success"
            })

        except Exception as e:
            logger.error(f"Error executing command {command_id}: {e}")
            await self.ack_command(command_id, "failed", str(e))

    def _execute_thrust(self, device_id: str, params: dict):
        """Execute thrust command on device"""
        x = params.get("x", 0)
        y = params.get("y", 0)
        z = params.get("z", 0)
        logger.info(f"  Thrusting {device_id} with vector ({x}, {y}, {z})")

    async def ack_command(self, command_id: str, status: str, error: str = None):
        """Send acknowledgment back to backend"""
        try:
            ack_data = {
                "status": status,
                "error": error
            }
            response = requests.post(
                f"{BACKEND_URL}/commands/pending/{command_id}/ack",
                json=ack_data,
                timeout=5
            )
            response.raise_for_status()
            logger.info(f"Command {command_id} acknowledged: {status}")
        except Exception as e:
            logger.error(f"Error acknowledging command {command_id}: {e}")

    async def start_polling(self, interval: int = 2):
        """Start polling backend at regular intervals"""
        logger.info(f"Starting command polling (interval: {interval}s)")
        while True:
            await self.poll_backend()
            await asyncio.sleep(interval)

    def get_status(self) -> dict:
        """Get command handler status"""
        import time
        return {
            "status": "running",
            "executed_commands": len(self.executed_commands),
            "backend_url": BACKEND_URL,
            "timestamp": int(time.time())
        }
