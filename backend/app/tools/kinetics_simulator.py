from __future__ import annotations

import numpy as np
from scipy.integrate import odeint
import math

from ..schemas import SimulationInputs, SimulationPoint, SimulationResult

# Thermodynamic Constants (J/mol O2)
def delta_g_si(T): return -910000 + 180 * T
def delta_g_ti(T): return -940000 + 180 * T
def delta_g_v(T):  return -800000 + 150 * T
def delta_g_c(T):  return -220000 - 170 * T
def delta_g_fe(T): return -500000 + 110 * T

# Molar Masses
M_C = 12.01
M_Si = 28.09
M_V = 50.94
M_Ti = 47.87
M_Fe = 55.85
M_O2 = 32.00

# Heat of Reaction (J/kg of Element Oxidized)
H_REACTION_C = 9000.0 * 1000
H_REACTION_SI = 28000.0 * 1000
H_REACTION_TI = 20000.0 * 1000
H_REACTION_V = 16000.0 * 1000
H_REACTION_FE = 5000.0 * 1000

# Specific Heat Capacity (J/kg/K)
CP_STEEL = 760.0

def calculate_kinetics_derivatives(y, t, bath_weight_kg, mols_o2_per_s, heat_loss_w=200000.0):
    """
    Core Differential Equation Function for Vanadium Extraction Kinetics.
    Can be used by ODE solver or Step-wise Simulator.
    """
    C, Si, V, Ti, T_c, FeO, V2O5, SiO2 = y
    T_k = T_c + 273.15
    
    # Base Mass Transfer Coefficients (1/s)
    k_si_base = 0.003
    k_ti_base = 0.003
    k_v_base = 0.002
    k_c_base = 0.0005

    # Rate constants (1/s)
    r_si = k_si_base * max(0, Si)
    r_ti = k_ti_base * max(0, Ti)
    
    # Crossover Temp Check
    tc_transition = 1380.0
    temp_factor = (T_c - tc_transition) / 50.0
    sigmoid = 1 / (1 + np.exp(-temp_factor))
    
    # V oxidation preference at low T
    # C oxidation preference at high T
    r_v = k_v_base * max(0, V) * (1.5 - 1.0 * sigmoid)
    r_c = k_c_base * max(0, C) * (0.1 + 5.0 * sigmoid)
    
    r_fe = 0.001 # Background

    # Oxygen Demand (mol/s)
    # Using kg/mol for Molar Mass to match bath_weight_kg
    demand_o2_si = ((r_si / 100) * bath_weight_kg / (M_Si / 1000.0)) * 1.0
    demand_o2_ti = ((r_ti / 100) * bath_weight_kg / (M_Ti / 1000.0)) * 1.0
    demand_o2_v  = ((r_v / 100) * bath_weight_kg / (M_V / 1000.0)) * 0.75
    demand_o2_c  = ((r_c / 100) * bath_weight_kg / (M_C / 1000.0)) * 0.5
    demand_o2_fe = ((r_fe / 100) * bath_weight_kg / (M_Fe / 1000.0)) * 0.5
    
    total_demand = demand_o2_si + demand_o2_ti + demand_o2_v + demand_o2_c + demand_o2_fe
    
    factor = 1.0
    if total_demand > mols_o2_per_s:
        factor = mols_o2_per_s / total_demand
    
    # Actual Rates
    real_o2_si = demand_o2_si * factor
    real_o2_ti = demand_o2_ti * factor
    real_o2_v  = demand_o2_v * factor
    real_o2_c  = demand_o2_c * factor
    
    # d[%]/dt
    dSidt = - (real_o2_si * 1.0 * M_Si / 1000) / bath_weight_kg * 100
    dTidt = - (real_o2_ti * 1.0 * M_Ti / 1000) / bath_weight_kg * 100
    dVdt  = - (real_o2_v * (4/3) * M_V / 1000) / bath_weight_kg * 100
    dCdt  = - (real_o2_c * 2.0 * M_C / 1000) / bath_weight_kg * 100
    
    # Heat Balance
    m_dot_si = abs(dSidt) / 100 * bath_weight_kg
    m_dot_ti = abs(dTidt) / 100 * bath_weight_kg
    m_dot_v  = abs(dVdt) / 100 * bath_weight_kg
    m_dot_c  = abs(dCdt) / 100 * bath_weight_kg
    
    heat_gen = (m_dot_si * H_REACTION_SI + 
                m_dot_ti * H_REACTION_TI + 
                m_dot_v * H_REACTION_V + 
                m_dot_c * H_REACTION_C)
                
    # Cooling
    coolant_load = 0.0
    if t < 300: # First 5 mins
        coolant_load = 3000000.0 # 3 MW
        
    net_heat = heat_gen - heat_loss_w - coolant_load
    dTdt = net_heat / (bath_weight_kg * CP_STEEL)
    
    # Slag
    dFeOdt = 0.05
    dV2O5dt = abs(dVdt) * 1.5
    dSiO2dt = abs(dSidt) * 2.0
    
    return [dCdt, dSidt, dVdt, dTidt, dTdt, dFeOdt, dV2O5dt, dSiO2dt]


def simulate_blow_path(inp: SimulationInputs) -> SimulationResult:
    """
    L2 动态仿真层 (ODE): 基于动力学微分方程推演熔池状态变化。
    使用基于吉布斯自由能(Delta G)的竞争氧化机制，模拟"保碳提钒"过程。
    """
    
    # --- Initialization ---
    mode = "real-data"
    initial_Si = inp.initial_analysis.Si
    initial_Ti = inp.initial_analysis.Ti
    
    # Soft sensing fallback
    if initial_Si < 0.01 or initial_Ti < 0.01:
        mode = "soft-sensing"
        initial_Si = 0.22 if initial_Si < 0.01 else initial_Si
        initial_Ti = 0.12 if initial_Ti < 0.01 else initial_Ti

    y0 = [
        inp.initial_analysis.C,
        initial_Si,
        inp.initial_analysis.V,
        initial_Ti,
        inp.initial_temp_c,
        5.0,
        0.0,
        1.0
    ]
    
    bath_weight_kg = 100.0 * 1000
    if inp.recipe and "iron_weight" in inp.recipe:
        bath_weight_kg = inp.recipe["iron_weight"] * 1000
        
    oxygen_flow_m3_s = inp.oxygen_flow_rate_m3h / 3600.0
    mols_o2_per_s = oxygen_flow_m3_s / 0.0224
    
    t_eval = np.linspace(0, inp.duration_s, inp.duration_s // 10 + 1)
    
    def wrapper(y, t):
        return calculate_kinetics_derivatives(y, t, bath_weight_kg, mols_o2_per_s)

    # Solve
    sol = odeint(wrapper, y0, t_eval)
    
    # Process Results
    points = []
    tc_crossover_s = None
    
    for i, ts in enumerate(t_eval):
        curr_t = sol[i, 4]
        if tc_crossover_s is None and curr_t >= 1360.0:
             tc_crossover_s = int(ts)
             
        point = SimulationPoint(
            time_s=int(ts),
            C_pct=max(0, round(sol[i, 0], 3)),
            Si_pct=max(0, round(sol[i, 1], 3)),
            V_pct=max(0, round(sol[i, 2], 3)),
            Ti_pct=max(0, round(sol[i, 3], 3)),
            temp_c=round(sol[i, 4], 1),
            FeO_pct=round(sol[i, 5], 2),
            V2O5_pct=round(sol[i, 6], 2),
            SiO2_pct=round(sol[i, 7], 2)
        )
        points.append(point)

    proactive_advice = None
    if tc_crossover_s:
         proactive_advice = f"预测 Tc 点 ({tc_crossover_s}s) 即将到达，建议准备提枪或加入冷却剂以抑制碳氧化。"
    
    return SimulationResult(
        points=points,
        tc_crossover_s=tc_crossover_s,
        final_temp_c=round(sol[-1, 4], 1),
        final_analysis={
            "C": max(0, round(sol[-1, 0], 3)),
            "Si": max(0, round(sol[-1, 1], 3)),
            "V": max(0, round(sol[-1, 2], 3)),
            "Ti": max(0, round(sol[-1, 3], 3)),
            "Slag_FeO": round(sol[-1, 5], 2),
            "Slag_V2O5": round(sol[-1, 6], 2),
            "Slag_SiO2": round(sol[-1, 7], 2)
        },
        proactive_advice=proactive_advice,
        mode=mode
    )
