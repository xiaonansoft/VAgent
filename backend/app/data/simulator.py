from __future__ import annotations

import asyncio
import random
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator, Optional

from pydantic import BaseModel
from ..core.config import settings


class SensorStatus(BaseModel):
    is_valid: bool = True
    raw_value: float | None = None
    estimated_value: float | None = None
    confidence: float = 1.0
    correction_source: str = "none"  # "none", "model", "history", "manual"


from .soft_sensor import SoftSensor

@dataclass
class SimState:
    # Process Time
    time_min: float = 0.0
    total_duration: float = 8.0  # Typical semi-steel vanadium extraction time

    # Chemistry (Percentage)
    c_pct: float = 3.50
    si_pct: float = 0.25
    v_pct: float = 0.35
    mn_pct: float = 0.20
    
    # Reaction Rates (stored for soft sensor input)
    d_si: float = 0.0
    d_c: float = 0.0
    
    # Temperature
    temp_c: float = 1280.0  # Initial temp for semi-steel
    
    # Control Variables
    lance_height_mm: float = 1100.0
    oxygen_flow_nm3_min: float = settings.oxygen_flow_nm3_h_default / 60.0 # ~366 Nm3/min
    coolant_added_kg: float = 0.0
    
    # Sensor Health (Simulated)
    # In reality, sensors are not continuous. We use "Soft Sensor" (Model) as primary.
    # We will simulate discrete "Sub-lance" measurements.
    
    # Sub-lance Measurements (Discrete Truth)
    # Stored as: { time_min: { temp: float, C: float, V: float } }
    latest_sample: dict | None = None
    
    # System Status
    is_emergency_stop: bool = False

    last_ts: datetime = field(default_factory=datetime.utcnow)


class DataSimulator:
    def __init__(self) -> None:
        self._state = SimState()
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        
        # Soft Sensor Module (Mechanism Inference)
        self.soft_sensor = SoftSensor()
        
        # Model Parameters (Self-Learning / Correction Factors)
        # In a real system, these would be loaded from a database where they were updated by ML models
        self.heat_efficiency_factor = settings.heat_efficiency_default  # Initial assumption
        self.reaction_rate_modifier = settings.reaction_rate_mod_default  # Slight boost to reaction rates based on recent heats

    @property
    def state(self) -> SimState:
        return self._state

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())
        
    def emergency_stop(self) -> None:
        self._state.is_emergency_stop = True
        # Immediate actions:
        # 1. Raise Lance
        self._state.lance_height_mm = 2000.0
        # 2. Stop Oxygen
        self._state.oxygen_flow_nm3_min = 0.0

    def resume(self) -> None:
        self._state.is_emergency_stop = False
        # Restore basic parameters
        self._state.lance_height_mm = 1100.0
        self._state.oxygen_flow_nm3_min = settings.oxygen_flow_nm3_h_default / 60.0

    async def _run(self) -> None:
        step_s = 1.0
        while True:
            await asyncio.sleep(step_s)
            async with self._lock:
                self._update_physics(step_s)
                payload = self._build_payload(step_s)
            
            self._broadcast(payload)

    def _update_physics(self, dt_s: float):
        s = self._state
        
        # 0. Emergency Stop Logic
        if s.is_emergency_stop:
            # Freeze time, stop reactions, just update timestamp
            s.last_ts = datetime.utcnow()
            # Slight cooling due to no reaction and open vessel
            s.temp_c -= 0.1 * (dt_s / 60.0) 
            return
        
        # 1. Advance Time
        dt_min = dt_s / 60.0
        s.time_min += dt_min
        s.last_ts = datetime.utcnow()

        # Reset if finished (Looping for demo)
        if s.time_min > s.total_duration + 2.0:
            self._reset_state()
            return

        # Reaction Kinetics (Simplified for Vanadium Extraction)
        # Order: Si > Mn > V > C (at low temp)
        # V oxidation is favored at low temp (< 1360), C oxidation favored at high temp
        
        # Reaction Rates (k) - strictly empirical for demo
        k_si = settings.k_si_base * self.reaction_rate_modifier
        k_mn = settings.k_mn_base * self.reaction_rate_modifier
        k_v = settings.k_v_base * self.reaction_rate_modifier
        k_c = settings.k_c_base  # C is slow initially
        
        # Temperature effect on V vs C (Critical Temp ~1360C)
        # As Temp rises, k_v decreases, k_c increases
        temp_factor = (s.temp_c - settings.temp_critical_v_c_switch) / 100.0 
        # If temp < 1360 (factor < 0), V is fast. If temp > 1360, V slows down.
        
        if temp_factor > 0:
            k_v *= max(0.1, 1.0 - temp_factor * 2) # Suppress V oxidation at high temp
            k_c *= (1.0 + temp_factor * 5)         # Accelerate C oxidation at high temp
        
        # Apply reductions
        d_si = k_si * s.si_pct * dt_min
        d_mn = k_mn * s.mn_pct * dt_min
        d_v = k_v * s.v_pct * dt_min
        d_c = k_c * s.c_pct * dt_min
        
        # Store rates for soft sensor
        s.d_si = d_si
        s.d_c = d_c
        
        s.si_pct = max(0.01, s.si_pct - d_si)
        s.mn_pct = max(0.05, s.mn_pct - d_mn)
        s.v_pct = max(0.05, s.v_pct - d_v)
        s.c_pct = max(3.0, s.c_pct - d_c)

        # 3. Thermal Balance
        # Exothermic heat from oxidation (kJ/kg roughly converted to Temp rise)
        # Si: Very high, V: High, C: Medium
        # Simplified coefficients: degrees per % oxidized
        heat_gen = (d_si * 180 + d_mn * 60 + d_v * 120 + d_c * 50) * self.heat_efficiency_factor
        
        # Heat Loss (Radiation + Convection)
        heat_loss = 0.5 * dt_min * (s.temp_c / 1400.0)
        
        # Coolant Effect (Simulated addition at min 3)
        coolant_effect = 0.0
        if 2.9 < s.time_min < 3.1:
             # Add coolant
             if s.coolant_added_kg < 1000:
                 added = 50.0 # kg
                 s.coolant_added_kg += added
                 coolant_effect = added * 0.5 # deg drop per kg (exaggerated)

        s.temp_c += (heat_gen - heat_loss - coolant_effect)
        
        # 4. Simulate Lance Movement Strategy
        if s.time_min < 1.0:
            s.lance_height_mm = 1100
        elif s.time_min < 5.0:
            s.lance_height_mm = 1200 # Raise to promote soft blow for V
        else:
            s.lance_height_mm = 1000

        # 5. Simulate Sub-lance Sampling (TSC/TSO)
        # TSC at 2.0 min, TSO at 7.0 min
        # Add random noise to simulate measurement error vs model error
        current_min = round(s.time_min, 1)
        if 1.95 <= current_min <= 2.05 or 6.95 <= current_min <= 7.05:
             # Only update if we haven't already for this window
             if not s.latest_sample or abs(s.latest_sample.get('time', -1) - current_min) > 0.5:
                 s.latest_sample = {
                     "time": current_min,
                     "temp": s.temp_c + random.uniform(-15, 15), # Deviation from model
                     "C": max(0.01, s.c_pct + random.uniform(-0.1, 0.1)),
                     "V": max(0.001, s.v_pct + random.uniform(-0.01, 0.01))
                 }
        
    def _reset_state(self):
        self._state = SimState()
        self._state.latest_sample = None # Reset samples
        # Randomize initial conditions slightly for variety
        self._state.temp_c = 1280 + random.uniform(-10, 10)
        self._state.si_pct = 0.25 + random.uniform(-0.05, 0.05)
        # Evolve model parameters (simulating "Self-Learning" from previous heat)
        # If efficiency was too high (temp overshot), reduce it. If too low, increase it.
        correction = random.uniform(-0.02, 0.02)
        self.heat_efficiency_factor = min(0.98, max(0.85, self.heat_efficiency_factor + correction))
        
        # Reset Soft Sensor history
        self.soft_sensor = SoftSensor()

    def _build_payload(self, dt_s: float) -> dict:
        s = self._state
        
        # 1. Model Calculated Value (Soft Sensor)
        raw_temp = s.temp_c
        
        # 2. Apply Soft Sensor (Mechanism Inference)
        # Pass the raw reading and auxiliary signals (reaction rates) to the soft sensor
        # We need to pass the rate per minute, so we divide the delta by dt_min
        dt_min = dt_s / 60.0
        si_rate = s.d_si / dt_min if dt_min > 0 else 0
        c_rate = s.d_c / dt_min if dt_min > 0 else 0

        sensor_result = self.soft_sensor.process(
            raw_temp=raw_temp,
            si_rate=si_rate, 
            c_rate=c_rate,
            dt_s=dt_s
        )
        
        # Construct Status Object
        temp_status = SensorStatus(
            is_valid=sensor_result['is_valid'],
            raw_value=sensor_result['raw_value'],
            estimated_value=sensor_result['estimated_value'],
            confidence=sensor_result['confidence'],
            correction_source=sensor_result['correction_source']
        )

        return {
            "process_time": round(s.time_min, 2),
            "temperature": {
                "value": round(temp_status.estimated_value if not temp_status.is_valid else temp_status.raw_value, 1),
                "status": temp_status.model_dump(),
                "ts": s.last_ts.isoformat()
            },
            "chemistry": {
                "si": round(s.si_pct, 3),
                "v": round(s.v_pct, 3),
                "c": round(s.c_pct, 2)
            },
            "lance_height": {
                "value": s.lance_height_mm,
                "ts": s.last_ts.isoformat()
            },
            "model_params": {
                "heat_efficiency": round(self.heat_efficiency_factor, 3),
                "reaction_rate_mod": round(self.reaction_rate_modifier, 3)
            },
            "is_emergency_stop": s.is_emergency_stop,
            "latest_sample": s.latest_sample
        }

    def _broadcast(self, payload: dict):
        for q in list(self._subscribers):
            if q.full():
                continue
            q.put_nowait(payload)

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=32)
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)
