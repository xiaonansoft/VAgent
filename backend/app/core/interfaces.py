from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from pydantic import BaseModel

class SensorStatus(BaseModel):
    is_valid: bool = True
    raw_value: float | None = None
    estimated_value: float | None = None
    confidence: float = 1.0
    correction_source: str = "none"

class IProcessDataReader(ABC):
    """
    Interface for reading process data (Temperature, Chemistry, etc.)
    """
    @abstractmethod
    async def get_temperature(self) -> SensorStatus:
        pass

    @abstractmethod
    async def get_chemistry(self) -> Dict[str, float]:
        pass

    @abstractmethod
    async def get_process_time(self) -> float:
        pass
        
    @abstractmethod
    async def get_lance_height(self) -> float:
        pass

    @abstractmethod
    async def get_oxygen_flow(self) -> float:
        pass

class IControlSignalWriter(ABC):
    """
    Interface for sending control signals (Lance, Oxygen, Coolant)
    """
    @abstractmethod
    async def set_lance_height(self, target_mm: float) -> bool:
        pass

    @abstractmethod
    async def set_oxygen_flow(self, flow_nm3_min: float) -> bool:
        pass

    @abstractmethod
    async def add_coolant(self, material: str, weight_kg: float) -> bool:
        pass

    @abstractmethod
    async def emergency_stop(self) -> bool:
        pass
