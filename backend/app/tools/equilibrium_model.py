from __future__ import annotations
from app.schemas import SimulationInputs, SimulationResult, SimulationPoint

def calculate_equilibrium_state(inp: SimulationInputs) -> dict:
    """
    Thermodynamic Equilibrium Model (L2-Eq)
    Calculates the theoretical final state based on oxygen balance and thermodynamic affinity order.
    Order of Oxidation: Si > Ti > V > C
    """
    
    # 1. Calculate Molar Amounts (in 100g basis for simplicity, or actual mass)
    iron_weight_kg = 1000.0 # Basis calculation
    
    # Initial masses
    mass_Si = iron_weight_kg * (inp.initial_analysis.Si / 100.0)
    mass_Ti = iron_weight_kg * (inp.initial_analysis.Ti / 100.0)
    mass_V = iron_weight_kg * (inp.initial_analysis.V / 100.0)
    mass_C = iron_weight_kg * (inp.initial_analysis.C / 100.0)
    
    # Molar masses (g/mol)
    M_Si, M_Ti, M_V, M_C, M_O2 = 28.09, 47.87, 50.94, 12.01, 32.00
    
    mols_Si = (mass_Si * 1000) / M_Si
    mols_Ti = (mass_Ti * 1000) / M_Ti
    mols_V = (mass_V * 1000) / M_V
    mols_C = (mass_C * 1000) / M_C
    
    # Total Oxygen Supplied (m3 -> mol)
    # 1 mol gas = 22.4 L = 0.0224 m3
    total_oxygen_m3 = (inp.oxygen_flow_rate_m3h / 3600.0) * inp.duration_s
    # Scale oxygen to our 1000kg basis (assuming inp.oxygen_flow is for the whole furnace)
    # We need the actual furnace size. 
    # Let's assume the flow rate provided is for the whole furnace, but we don't know the furnace size in SimulationInputs?
    # Actually InitialChargeInputs has iron_weight_t. SimulationInputs does not.
    # We'll assume a standard 100t furnace for the ratio if not provided, 
    # OR we can assume the inputs are proportional.
    # Let's check InitialChargeInputs... it has iron_weight_t.
    # SimulationInputs usually comes after InitialCharge, but it doesn't have weight.
    # We will assume a fixed ratio or that flow_rate is matched to the weight.
    # Let's just use the flow rate as given and assume a standard batch size of 100t for the simulation context 
    # if it's not explicitly passed. 
    # Wait, `kinetics_simulator` uses percentages and rate constants, it doesn't strictly depend on mass 
    # except for heat capacity (which cancels out if per kg).
    # But for Equilibrium, we need the Oxygen/Mass ratio.
    # Let's assume 100 tons iron for the calculation to be consistent with typical flow rates (22000 m3/h is typical for ~100t).
    
    assumed_iron_weight_t = 100.0
    scaling_factor = 1000.0 / (assumed_iron_weight_t * 1000.0) # Scale O2 down to 1000kg basis
    
    total_oxygen_mols = (total_oxygen_m3 / 0.0224) * scaling_factor
    
    # 2. Consume Oxygen by Affinity
    
    # Si + O2 -> SiO2 (1:1)
    react_Si = min(mols_Si, total_oxygen_mols)
    mols_Si -= react_Si
    total_oxygen_mols -= react_Si
    
    # Ti + O2 -> TiO2 (1:1)
    react_Ti = 0.0
    if total_oxygen_mols > 0:
        react_Ti = min(mols_Ti, total_oxygen_mols)
        mols_Ti -= react_Ti
        total_oxygen_mols -= react_Ti
        
    # 4V + 3O2 -> 2V2O3 (V:O2 = 4:3 = 1:0.75) => 1 mol V consumes 0.75 mol O2
    react_V = 0.0
    if total_oxygen_mols > 0:
        max_react_V = total_oxygen_mols / 0.75
        react_V = min(mols_V, max_react_V)
        mols_V -= react_V
        total_oxygen_mols -= react_V * 0.75
        
    # 2C + O2 -> 2CO (C:O2 = 2:1 = 1:0.5) => 1 mol C consumes 0.5 mol O2
    react_C = 0.0
    if total_oxygen_mols > 0:
        max_react_C = total_oxygen_mols / 0.5
        react_C = min(mols_C, max_react_C)
        mols_C -= react_C
        total_oxygen_mols -= react_C * 0.5
        
    # 3. Calculate Final Compositions
    final_Si_pct = (mols_Si * M_Si / 1000.0) / iron_weight_kg * 100.0
    final_Ti_pct = (mols_Ti * M_Ti / 1000.0) / iron_weight_kg * 100.0
    final_V_pct = (mols_V * M_V / 1000.0) / iron_weight_kg * 100.0
    final_C_pct = (mols_C * M_C / 1000.0) / iron_weight_kg * 100.0
    
    # 4. Calculate Heat Balance
    # Reaction Heats (kJ/mol) - Approximate
    H_Si = 858.0 # kJ/mol Si
    H_Ti = 944.0 # kJ/mol Ti
    H_V = 750.0 # kJ/mol V (approx for V2O3)
    H_C = 110.0 # kJ/mol C (partial oxidation to CO)
    
    total_heat_gen_kJ = (react_Si * H_Si) + (react_Ti * H_Ti) + (react_V * H_V) + (react_C * H_C)
    
    # Heat Loss (assume 10% of generated heat is lost to vessel/slag)
    effective_heat_kJ = total_heat_gen_kJ * 0.9
    
    # Coolant Heat Consumption
    # Assume coolant is Scrap/Pig Iron mix, approx melting heat 1400 kJ/kg
    # Total coolant in recipe (scaled to 1000kg basis)
    total_coolant_t = sum(inp.recipe.values())
    coolant_ratio = total_coolant_t / assumed_iron_weight_t # t/t
    coolant_mass_basis = coolant_ratio * iron_weight_kg
    
    heat_consumed_coolant_kJ = coolant_mass_basis * 1400.0
    
    net_heat_kJ = effective_heat_kJ - heat_consumed_coolant_kJ
    
    # Temperature Rise
    # Cp of molten iron ~ 0.8 kJ/kg.K
    # Mass = 1000kg + coolant (approx, but coolant becomes part of melt)
    total_mass = iron_weight_kg + coolant_mass_basis
    delta_T = net_heat_kJ / (total_mass * 0.82)
    
    final_temp = inp.initial_temp_c + delta_T
    
    return {
        "final_temp_c": round(final_temp, 1),
        "final_analysis": {
            "C": round(final_C_pct, 3),
            "Si": round(final_Si_pct, 3),
            "V": round(final_V_pct, 3),
            "Ti": round(final_Ti_pct, 3)
        }
    }
