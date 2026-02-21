from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict
import logging
import asyncio
from pydantic import BaseModel

from .interfaces import IProcessDataReader, IControlSignalWriter, SensorStatus
from ..data.simulator import DataSimulator

# --- Enums ---
class SystemMode(str, Enum):
    SIMULATION = "SIMULATION"
    VALIDATION = "VALIDATION"  # Shadow Mode
    PRODUCTION = "PRODUCTION"

# --- Concrete Implementations: Simulation ---
class SimulationDataReader(IProcessDataReader):
    def __init__(self, simulator: DataSimulator):
        self.sim = simulator

    async def get_temperature(self) -> SensorStatus:
        # In simulation, we trust the model (soft sensor) or simulated sensor
        state = self.sim.state
        # For simplicity, returning the soft sensor value or simulated value
        return SensorStatus(
            is_valid=True,
            estimated_value=state.temp_c,
            confidence=0.95,
            correction_source="simulation"
        )

    async def get_chemistry(self) -> Dict[str, float]:
        state = self.sim.state
        return {
            "C": state.c_pct,
            "Si": state.si_pct,
            "V": state.v_pct,
            "Mn": state.mn_pct
        }

    async def get_process_time(self) -> float:
        return self.sim.state.time_min

    async def get_lance_height(self) -> float:
        return self.sim.state.lance_height_mm

    async def get_oxygen_flow(self) -> float:
        return self.sim.state.oxygen_flow_nm3_min

class SimulationControlWriter(IControlSignalWriter):
    def __init__(self, simulator: DataSimulator):
        self.sim = simulator

    async def set_lance_height(self, target_mm: float) -> bool:
        self.sim.state.lance_height_mm = target_mm
        return True

    async def set_oxygen_flow(self, flow_nm3_min: float) -> bool:
        self.sim.state.oxygen_flow_nm3_min = flow_nm3_min
        return True

    async def add_coolant(self, material: str, weight_kg: float) -> bool:
        self.sim.state.coolant_added_kg += weight_kg
        return True

    async def emergency_stop(self) -> bool:
        self.sim.emergency_stop()
        return True

# --- Concrete Implementations: Validation (Shadow) ---
class ValidationDataReader(IProcessDataReader):
    """
    Reads from real production data stream (Mocked for now).
    """
    async def get_temperature(self) -> SensorStatus:
        # TODO: Connect to Real Kafka/OPC-UA
        return SensorStatus(is_valid=False, confidence=0.0) 

    async def get_chemistry(self) -> Dict[str, float]:
        return {"C": 0.0, "Si": 0.0, "V": 0.0}

    async def get_process_time(self) -> float:
        return 0.0
        
    async def get_lance_height(self) -> float:
        return 0.0

    async def get_oxygen_flow(self) -> float:
        return 0.0

class ValidationControlWriter(IControlSignalWriter):
    """
    SAFEGUARD: Log-only writer. Physically incapable of sending signals to DCS.
    """
    def __init__(self):
        self.logger = logging.getLogger("ValidationAudit")
        self.logs = [] # In-memory log for testing

    async def set_lance_height(self, target_mm: float) -> bool:
        msg = f"[VALIDATION] Would set lance height to {target_mm}mm"
        self.logger.info(msg)
        self.logs.append(msg)
        return True # Pretend success

    async def set_oxygen_flow(self, flow_nm3_min: float) -> bool:
        msg = f"[VALIDATION] Would set oxygen flow to {flow_nm3_min} Nm3/min"
        self.logger.info(msg)
        self.logs.append(msg)
        return True

    async def add_coolant(self, material: str, weight_kg: float) -> bool:
        msg = f"[VALIDATION] Would add {weight_kg}kg of {material}"
        self.logger.info(msg)
        self.logs.append(msg)
        return True

    async def emergency_stop(self) -> bool:
        msg = "[VALIDATION] Would trigger EMERGENCY STOP"
        self.logger.critical(msg)
        self.logs.append(msg)
        return True

# --- Concrete Implementations: Production ---
class ProductionControlWriter(IControlSignalWriter):
    """
    Real DCS Interface.
    """
    def __init__(self, dcs_client=None):
        self.dcs_client = dcs_client

    async def set_lance_height(self, target_mm: float) -> bool:
        # if not self.dcs_client: raise ConnectionError("DCS Disconnected")
        # await self.dcs_client.write_tag("LANCE_H_SP", target_mm)
        raise NotImplementedError("DCS Connection not implemented yet - SAFETY LOCK")

    async def set_oxygen_flow(self, flow_nm3_min: float) -> bool:
        raise NotImplementedError("DCS Connection not implemented yet - SAFETY LOCK")

    async def add_coolant(self, material: str, weight_kg: float) -> bool:
        raise NotImplementedError("DCS Connection not implemented yet - SAFETY LOCK")

    async def emergency_stop(self) -> bool:
        raise NotImplementedError("DCS Connection not implemented yet - SAFETY LOCK")

# --- Mode Controller ---

class ModeSwitchRecord(BaseModel):
    timestamp: datetime
    user: str
    from_mode: SystemMode
    to_mode: SystemMode
    reason: str

class ModeController:
    def __init__(self, simulator: Optional[DataSimulator] = None):
        self._mode = SystemMode.SIMULATION
        self._simulator = simulator or DataSimulator()
        
        # Default to Simulation
        self.reader: IProcessDataReader = SimulationDataReader(self._simulator)
        self.writer: IControlSignalWriter = SimulationControlWriter(self._simulator)
        
        self.audit_log: List[ModeSwitchRecord] = []
        self._logger = logging.getLogger("ModeController")
        
        # Concurrency & Rate Limiting
        self._lock = asyncio.Lock()
        self._last_switch_time = 0.0
        self._switch_cooldown = 1.0 # Seconds

    @property
    def current_mode(self) -> SystemMode:
        return self._mode

    async def switch_mode(self, new_mode: SystemMode, user: str, auth_token: str, reason: str = ""):
        """
        Switch system mode with strict auditing, safety checks, and rate limiting.
        """
        async with self._lock:
            current_time = asyncio.get_event_loop().time()
            if current_time - self._last_switch_time < self._switch_cooldown:
                raise RuntimeError(f"Mode switch too frequent. Please wait {self._switch_cooldown}s.")

            if new_mode == self._mode:
                return

            # 1. State Machine Validation
            if self._mode == SystemMode.SIMULATION and new_mode == SystemMode.PRODUCTION:
                raise ValueError("Illegal State Transition: Cannot switch directly from SIMULATION to PRODUCTION. Must go through VALIDATION.")

            # 2. Security Check
            if new_mode == SystemMode.PRODUCTION:
                if auth_token != "SECURE_PRODUCTION_TOKEN_2026": # Placeholder for real token validation
                    raise PermissionError("Invalid Auth Token for PRODUCTION mode")
            
            # 3. Strategy Switch (Dependency Injection)
            # Atomic update of reader/writer references within the lock
            if new_mode == SystemMode.SIMULATION:
                self.reader = SimulationDataReader(self._simulator)
                self.writer = SimulationControlWriter(self._simulator)
            
            elif new_mode == SystemMode.VALIDATION:
                self.reader = ValidationDataReader() # TODO: Inject real reader
                self.writer = ValidationControlWriter()
                
            elif new_mode == SystemMode.PRODUCTION:
                self.reader = ValidationDataReader() # Uses real reader too
                self.writer = ProductionControlWriter() # The real deal

            # 4. Audit Logging & State Update
            record = ModeSwitchRecord(
                timestamp=datetime.utcnow(),
                user=user,
                from_mode=self._mode,
                to_mode=new_mode,
                reason=reason
            )
            self.audit_log.append(record)
            self._logger.warning(f"Mode Switch: {self._mode} -> {new_mode} by {user}")
            
            self._mode = new_mode
            self._last_switch_time = current_time
