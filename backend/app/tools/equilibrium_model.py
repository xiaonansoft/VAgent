from __future__ import annotations
from typing import Dict, Any
from app.schemas import SimulationInputs

# Danieli SDM Constants (Consistent with thermal_balance.py)
C_SP_HM = 0.88      # MJ/°C/t
H_HM_0 = 42.0       # MJ/t
C_SP_ST = 0.76      # MJ/°C/t
H_ST_0 = 193.0      # MJ/t
C_SP_SLAG = 1.19    # MJ/°C/t
C_SP_SC = 0.46      # MJ/°C/t

# Reaction Heats (MJ/t of element)
H_R_C_CO = 7470.0
H_R_C_CO2 = 21285.0
H_R_SI = 27620.0
H_R_MN = 5530.0
H_R_P = 26160.0
H_R_FE = 3135.0
H_R_V = 15000.0     # Estimated for V -> V2O3/V2O5 (Need verification, using approx)
H_R_TI = 19000.0    # Estimated for Ti -> TiO2

# Atomic Weights
M_C = 12.01
M_SI = 28.09
M_MN = 54.94
M_P = 30.97
M_S = 32.06
M_FE = 55.85
M_V = 50.94
M_TI = 47.87
M_O = 16.00

def calculate_equilibrium_state(inp: SimulationInputs) -> Dict[str, Any]:
    """
    Danieli SDM Equilibrium Model (Four Balances Implementation)
    1. Material Balance
    2. Oxygen Balance
    3. Slag Balance
    4. Thermal Balance
    """
    
    # --- 1. Material Balance (Inputs) ---
    # Assume standard furnace size if not provided, or derive from recipe
    # In SimulationInputs, we have `recipe`. Let's assume `recipe` contains weights in tons.
    # If recipe is empty or doesn't have 'iron_weight', we default to 100t.
    
    iron_weight_t = inp.recipe.get("iron_weight", 100.0)
    scrap_weight_t = inp.recipe.get("scrap_weight", 10.0)
    lime_weight_t = inp.recipe.get("lime_weight", 3.0) # Additive
    ore_weight_t = inp.recipe.get("ore_weight", 1.0)   # Coolant/Oxidizer
    
    total_input_metal_t = iron_weight_t + scrap_weight_t
    
    # Initial Masses (kg)
    # Iron Analysis
    m_si_init = iron_weight_t * 1000 * (inp.initial_analysis.Si / 100.0)
    m_c_init = iron_weight_t * 1000 * (inp.initial_analysis.C / 100.0)
    m_v_init = iron_weight_t * 1000 * (inp.initial_analysis.V / 100.0)
    m_ti_init = iron_weight_t * 1000 * (inp.initial_analysis.Ti / 100.0)
    m_mn_init = iron_weight_t * 1000 * 0.002 # Assume 0.2% Mn if not in analysis
    m_p_init = iron_weight_t * 1000 * (inp.initial_analysis.P / 100.0)
    
    # Scrap Contribution (Assume Scrap is pure Fe for simplicity, or has similar C/Si)
    # For now, assume Scrap is low C, low Si steel.
    m_c_init += scrap_weight_t * 1000 * 0.001 # 0.1% C
    
    # --- 2. Oxygen Balance ---
    # Total Oxygen Supplied (m3)
    total_oxygen_m3 = (inp.oxygen_flow_rate_m3h / 3600.0) * inp.duration_s
    
    # Oxygen from Ore (Fe2O3 -> Fe + O)
    # Assume Ore is 70% Fe2O3. 
    # Fe2O3: 2*56 + 3*16 = 112 + 48 = 160. O is 48/160 = 30%.
    # But usually Ore is defined by Fe content. Let's assume 30% O by weight availability.
    o2_from_ore_kg = ore_weight_t * 1000 * 0.30
    # Convert kg O to m3 O2. 1 mol O2 = 32g. 1 mol = 22.4L.
    # 1 kg O2 = 1000/32 mol = 31.25 mol. Volume = 31.25 * 0.0224 = 0.7 m3.
    # Wait, 1 kg O = 1/2 kg O2? No, mass is mass.
    # O2 gas: 32g/mol. O atom: 16g/mol.
    # o2_from_ore_kg is mass of Oxygen atoms.
    # Moles of O atoms = o2_from_ore_kg * 1000 / 16.
    # Moles of O2 gas equivalent = Moles O / 2.
    # Volume = Moles O2 * 0.0224 m3.
    mols_o_ore = (o2_from_ore_kg * 1000) / 16.0
    mols_o2_ore = mols_o_ore / 2.0
    vol_o2_ore = mols_o2_ore * 0.0224
    
    total_o2_available_m3 = total_oxygen_m3 + vol_o2_ore
    total_o2_mols = total_o2_available_m3 / 0.0224
    
    # Oxidation Priority (Thermodynamic Affinity): Si > Ti > V > C > P > Fe (Simplified)
    # Danieli Model uses specific coefficients (SoxE).
    # We will simulate consumption based on stoichiometry.
    
    # 2.1 Si + O2 -> SiO2
    mols_si = (m_si_init * 1000) / M_SI # g -> mol
    o2_req_si = mols_si # 1:1 ratio
    
    react_si_mols = min(mols_si, total_o2_mols)
    total_o2_mols -= react_si_mols
    m_si_final = 0.0 if react_si_mols == mols_si else (mols_si - react_si_mols) * M_SI / 1000
    
    # 2.2 Ti + O2 -> TiO2
    mols_ti = (m_ti_init * 1000) / M_TI
    o2_req_ti = mols_ti # 1:1
    
    react_ti_mols = 0.0
    if total_o2_mols > 0:
        react_ti_mols = min(mols_ti, total_o2_mols)
        total_o2_mols -= react_ti_mols
    m_ti_final = 0.0 if react_ti_mols == mols_ti else (mols_ti - react_ti_mols) * M_TI / 1000
        
    # 2.3 4V + 3O2 -> 2V2O3 (or V2O5? Danieli mentions V recovery. Usually V -> V2O3 in converter)
    # Let's assume V + 0.75 O2 -> 0.5 V2O3
    mols_v = (m_v_init * 1000) / M_V
    o2_req_v = mols_v * 0.75
    
    react_v_mols = 0.0
    if total_o2_mols > 0:
        max_v_react = total_o2_mols / 0.75
        react_v_mols = min(mols_v, max_v_react)
        total_o2_mols -= react_v_mols * 0.75
    m_v_final = (mols_v - react_v_mols) * M_V / 1000
        
    # 2.4 2C + O2 -> 2CO (Partial oxidation primarily)
    # Danieli mentions PCO2 factor. Let's assume 10% CO2, 90% CO.
    # C + 0.5 O2 -> CO
    # C + 1.0 O2 -> CO2
    # Avg O2 per C = 0.9*0.5 + 0.1*1.0 = 0.45 + 0.1 = 0.55 mol O2 per mol C.
    mols_c = (m_c_init * 1000) / M_C
    o2_req_c = mols_c * 0.55
    
    react_c_mols = 0.0
    if total_o2_mols > 0:
        max_c_react = total_o2_mols / 0.55
        react_c_mols = min(mols_c, max_c_react)
        total_o2_mols -= react_c_mols * 0.55
    m_c_final = (mols_c - react_c_mols) * M_C / 1000
        
    # 2.5 Fe + 0.5 O2 -> FeO
    # Remaining oxygen oxidizes Fe
    react_fe_mols = 0.0
    if total_o2_mols > 0:
        react_fe_mols = total_o2_mols / 0.5 # 1 mol O2 oxidizes 2 mol Fe
        # Check if we have enough Fe? Usually yes.
    
    # --- 3. Slag Balance ---
    # Calculate Oxides
    # SiO2: 60.08 g/mol
    m_sio2 = react_si_mols * 60.08 / 1000 # kg
    # TiO2: 79.87 g/mol
    m_tio2 = react_ti_mols * 79.87 / 1000
    # V2O3: 149.88 g/mol (0.5 mol per mol V)
    m_v2o3 = (react_v_mols * 0.5) * 149.88 / 1000
    # FeO: 71.85 g/mol
    m_feo = react_fe_mols * 71.85 / 1000
    
    # Additives
    # Lime (CaO)
    m_cao = lime_weight_t * 1000 # Assume pure CaO for simplicity
    
    total_slag_kg = m_sio2 + m_tio2 + m_v2o3 + m_feo + m_cao
    
    # --- 4. Thermal Balance ---
    # Heat Input
    # Iron Sensible Heat
    h_hm = C_SP_HM * inp.initial_temp_c + H_HM_0
    H_input_hm = h_hm * iron_weight_t # MJ
    
    # Reaction Heats
    H_gen_si = (react_si_mols * M_SI / 1000 / 1000) * H_R_SI * 1000 # mol -> ton -> MJ? 
    # H_R_SI is MJ/t. react_si_mols * M_SI is grams. /1000 -> kg. /1000 -> ton.
    # Let's simplify: Mass reacted (t) * H_R (MJ/t)
    
    w_si_reacted_t = (react_si_mols * M_SI) / 1e6
    w_ti_reacted_t = (react_ti_mols * M_TI) / 1e6
    w_v_reacted_t = (react_v_mols * M_V) / 1e6
    w_c_reacted_t = (react_c_mols * M_C) / 1e6
    w_fe_reacted_t = (react_fe_mols * M_FE) / 1e6
    
    H_gen_si = w_si_reacted_t * H_R_SI
    H_gen_ti = w_ti_reacted_t * H_R_TI
    H_gen_v = w_v_reacted_t * H_R_V
    
    # C -> CO/CO2
    # 10% CO2
    h_c_avg = H_R_C_CO * 0.9 + H_R_C_CO2 * 0.1
    H_gen_c = w_c_reacted_t * h_c_avg
    
    H_gen_fe = w_fe_reacted_t * H_R_FE
    
    H_gen_total = H_gen_si + H_gen_ti + H_gen_v + H_gen_c + H_gen_fe
    
    # Heat Loss
    H_loss = 2000.0 # MJ Estimate
    
    # Heat Consumption (Scrap, Additives)
    # Scrap: Assume melts and reaches Final Temp.
    # Additives: Lime heating + dissolution.
    
    # We solve for T_final:
    # H_in + H_gen - H_loss = H_steel(T) + H_slag(T)
    # H_steel(T) = W_steel * (C_SP_ST * T + H_ST_0)
    # H_slag(T) = W_slag * (C_SP_SLAG * T)
    
    # Total available heat for products
    H_avail = H_input_hm + H_gen_total - H_loss
    
    # Subtract heat to heat scrap to 0 (base) -> Wait, Scrap H is 0 at 0C?
    # H_sc_input = C_SP_SC * (T_sc - 25) * W_sc. If T_sc=25, H=0.
    # But scrap needs to be heated to T_final.
    # So Scrap is part of W_steel.
    
    w_steel_final_t = total_input_metal_t - (w_c_reacted_t + w_si_reacted_t + w_ti_reacted_t + w_v_reacted_t + w_fe_reacted_t)
    w_slag_final_t = total_slag_kg / 1000.0
    
    # H_avail = w_steel * (0.76 * T + 193) + w_slag * (1.19 * T)
    # H_avail = T * (0.76 * w_steel + 1.19 * w_slag) + 193 * w_steel
    # T * (Factor) = H_avail - 193 * w_steel
    # T = (H_avail - 193 * w_steel) / Factor
    
    denom = (C_SP_ST * w_steel_final_t) + (C_SP_SLAG * w_slag_final_t)
    
    if denom > 0:
        final_temp_c = (H_avail - H_ST_0 * w_steel_final_t) / denom
    else:
        final_temp_c = inp.initial_temp_c # Fallback
    
    # --- Results ---
    
    final_analysis = {
        "C": (m_c_final / 1000 / w_steel_final_t) * 100.0,
        "Si": (m_si_final / 1000 / w_steel_final_t) * 100.0,
        "Ti": (m_ti_final / 1000 / w_steel_final_t) * 100.0,
        "V": (m_v_final / 1000 / w_steel_final_t) * 100.0,
    }
    
    slag_analysis = {
        "SiO2": (m_sio2 / total_slag_kg) * 100.0,
        "TiO2": (m_tio2 / total_slag_kg) * 100.0,
        "V2O3": (m_v2o3 / total_slag_kg) * 100.0,
        "FeO": (m_feo / total_slag_kg) * 100.0,
        "CaO": (m_cao / total_slag_kg) * 100.0,
    }
    
    return {
        "final_analysis": final_analysis,
        "slag_analysis": slag_analysis,
        "final_temp_c": round(final_temp_c, 1),
        "weights": {
            "steel_t": round(w_steel_final_t, 2),
            "slag_t": round(w_slag_final_t, 2),
        },
        "four_balances": {
            "material": {
                "input_t": total_input_metal_t,
                "output_steel_t": w_steel_final_t,
                "output_slag_t": w_slag_final_t,
            },
            "oxygen": {
                "total_supplied_m3": round(total_o2_available_m3, 1),
                "consumed_m3": round(total_oxygen_m3, 1), # Simplified
            },
            "thermal": {
                "input_mj": round(H_input_hm, 1),
                "generated_mj": round(H_gen_total, 1),
                "loss_mj": round(H_loss, 1),
                "output_mj": round(H_avail, 1),
            }
        }
    }
