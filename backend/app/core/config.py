from pydantic import BaseModel

class Settings(BaseModel):
    # --- Physical Constants (Specific Heat) ---
    cp_hm: float = 0.8  # kJ/(kg*K) Iron Specific Heat
    
    # --- Process Targets ---
    target_v_residual: float = 0.03  # % Target residual Vanadium
    target_c_oxidation_start: float = 3.5  # % Carbon level where oxidation starts contributing significantly
    
    # --- Enthalpies (kJ/kg) ---
    h_si_oxidation: float = 27620.0
    h_v_oxidation: float = 15200.0
    h_c_oxidation: float = 9280.0
    h_oxide_scale_absorption: float = 2000.0  # kJ/kg
    h_pig_iron_absorption: float = 1200.0  # kJ/kg
    
    # --- Slag & Oxygen Coefficients ---
    slag_coeff_si: float = 2.14
    slag_coeff_v: float = 1.79
    oxy_coeff_si: float = 0.8  # m3/kg
    oxy_coeff_v: float = 0.5   # m3/kg
    oxy_coeff_c: float = 0.93  # m3/kg
    
    # --- Simulation Kinetic Rates (Base) ---
    k_si_base: float = 2.0
    k_mn_base: float = 1.5
    k_v_base: float = 1.2
    k_c_base: float = 0.05
    
    # --- Simulation Control Parameters ---
    temp_critical_v_c_switch: float = 1360.0  # Temp where C oxidation overtakes V
    heat_efficiency_default: float = 0.92
    reaction_rate_mod_default: float = 1.05
    oxygen_flow_nm3_h_default: float = 22000.0  # Nm3/h
    
    # --- One-Can Process ---
    one_can_temp_boost: float = 30.0  # deg C

    # Heat Balance
    heat_loss_ratio: float = 0.05
    target_heat_efficiency: float = 0.85
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./vagent.db"

    # Slag Generation

settings = Settings()
