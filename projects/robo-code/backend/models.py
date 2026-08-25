from pydantic import BaseModel, Field
from typing import Optional

class TelemetryData(BaseModel):
    id: str = Field(..., example="sat_1")
    timestamp: int = Field(..., example=1705329045)
    sensors: dict = Field(..., example={"temp": 45.2, "battery": 89})
    azimuth: float = Field(..., example=1.57)
    elevation: float = Field(..., example=0.785)

class Command(BaseModel):
    device_id: str = Field(..., example="sat_1")
    action: str = Field(..., example="thrust")
    params: dict = Field(..., example={"x": 10.5, "y": 20.3, "z": -5.2})

class CommandAck(BaseModel):
    status: str = Field(..., example="executed")
    error: Optional[str] = Field(None, example=None)
