import numpy as np
from typing import Dict, Any, Optional

class SoftSensor:
    """
    Soft Sensor Module for Vanadium Extraction Process.
    
    Purpose:
    1. Detect anomalies in physical sensors (e.g., thermocouple failure).
    2. Reconstruct missing/invalid data using process mechanism models (Mass/Energy Balance).
    3. Provide confidence intervals for estimated values.
    """
    
    def __init__(self):
        # Physical constraints for validation
        self.TEMP_MIN = 1200.0
        self.TEMP_MAX = 1550.0
        self.TEMP_MAX_CHANGE_RATE = 50.0 # deg/min (sudden jumps are suspicious)
        
        # History for trend analysis
        self.last_valid_temp: Optional[float] = None
        self.last_temp_ts: float = 0.0
        
        # Correlation models (simplified linear regression coefficients for demo)
        # In real system, these would be learned from historical data
        # Delta_Temp ~ k1 * O2_Flow + k2 * Si_Oxidation + k3 * C_Oxidation
        self.energy_coeffs = {
            'base_loss': -5.0, # cooling rate
            'si_heat': 20.0,   # exothermic heat per unit Si
            'c_heat': 10.0     # exothermic heat per unit C
        }

    def validate_temperature(self, current_temp: float, dt_s: float) -> Dict[str, Any]:
        """
        Check if the current temperature reading is valid based on physical constraints.
        """
        status = {
            'is_valid': True,
            'reason': 'normal',
            'confidence': 1.0
        }
        
        # 1. Range Check
        if not (self.TEMP_MIN <= current_temp <= self.TEMP_MAX):
            status['is_valid'] = False
            status['reason'] = 'out_of_range'
            status['confidence'] = 0.0
            return status
            
        # 2. Rate of Change Check (if we have history)
        if self.last_valid_temp is not None and dt_s > 0:
            rate = abs(current_temp - self.last_valid_temp) / (dt_s / 60.0) # deg/min
            if rate > self.TEMP_MAX_CHANGE_RATE:
                status['is_valid'] = False
                status['reason'] = 'rate_exceeded'
                status['confidence'] = 0.2 # Low confidence, might be a real spike but unlikely
                return status
                
        return status

    def estimate_temperature(self, 
                             last_temp: float, 
                             si_rate: float, 
                             c_rate: float, 
                             dt_s: float) -> float:
        """
        Reconstruct temperature using Heat Balance Model (Soft Sensing).
        
        T_next = T_prev + (Heat_Reaction - Heat_Loss) / Heat_Capacity * dt
        """
        # Simplified heat balance logic
        # dTemp = (Heat from Si + Heat from C - Heat Loss) * dt
        
        # Normalize rates for calculation (arbitrary units for demo)
        heat_input = (si_rate * self.energy_coeffs['si_heat'] + 
                      c_rate * self.energy_coeffs['c_heat'])
        
        net_change = (heat_input + self.energy_coeffs['base_loss']) * (dt_s / 60.0)
        
        estimated_temp = last_temp + net_change
        return estimated_temp

    def process(self, 
                raw_temp: float, 
                si_rate: float, 
                c_rate: float, 
                dt_s: float) -> Dict[str, Any]:
        """
        Main entry point for sensor data processing.
        """
        validation = self.validate_temperature(raw_temp, dt_s)
        
        result = {
            'raw_value': raw_temp,
            'is_valid': validation['is_valid'],
            'estimated_value': raw_temp, # Default to raw if valid
            'correction_source': 'none',
            'confidence': validation['confidence']
        }
        
        if validation['is_valid']:
            self.last_valid_temp = raw_temp
        else:
            # Trigger Soft Sensing / Mechanism Inference
            if self.last_valid_temp is not None:
                estimated = self.estimate_temperature(self.last_valid_temp, si_rate, c_rate, dt_s)
                result['estimated_value'] = estimated
                result['correction_source'] = 'mechanism_inference' # 机理反推
                result['confidence'] = 0.85 # High but not perfect
                
                # Update history with estimated value to maintain continuity during long outages
                self.last_valid_temp = estimated 
            else:
                # Cold start failure - fallback
                result['estimated_value'] = 1300.0 
                result['correction_source'] = 'default_fallback'
                result['confidence'] = 0.1

        return result
