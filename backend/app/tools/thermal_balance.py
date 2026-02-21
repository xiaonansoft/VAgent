from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional

from ..schemas import CoolantRecommendation, CoolantType

# Danieli SDM Constants (MJ/t, MJ/°C/t)
C_SP_HM = 0.88      # Hot Metal Specific Heat
H_HM_0 = 42.0       # Hot Metal Enthalpy at 0°C
C_SP_ST = 0.76      # Steel Specific Heat
H_ST_0 = 193.0      # Steel Enthalpy at 0°C
C_SP_SLAG = 1.19    # Slag Specific Heat
C_SP_SC = 0.46      # Scrap Specific Heat
H_SC_0 = 0.0        # Scrap Enthalpy at 0°C (Assumption)

# Reaction Heats (MJ/t of element)
H_R_C_CO = 7470.0
H_R_C_CO2 = 21285.0
H_R_SI = 27620.0
H_R_MN = 5530.0
H_R_P = 26160.0
H_R_FE = 3135.0     # Fe -> FeO/Fe2O3 mix (Approx)

class ThermalBalanceInputs(BaseModel):
    # Hot Metal
    iron_temp_c: float = Field(..., ge=0, description="铁水温度")
    si_content_pct: float = Field(..., ge=0, description="铁水硅含量")
    mn_content_pct: float = Field(default=0.2, ge=0, description="铁水锰含量")
    p_content_pct: float = Field(default=0.1, ge=0, description="铁水磷含量")
    c_content_pct: float = Field(default=4.5, ge=0, description="铁水碳含量")
    hot_metal_weight_t: float = Field(default=100.0, ge=0, description="铁水重量(t)")
    
    # Process
    is_one_can: bool = Field(default=False, description="一罐到底模式")
    waiting_time_min: float = Field(default=5.0, ge=0, description="等待时间")
    
    # Scrap
    scrap_weight_t: float = Field(default=10.0, ge=0, description="废钢重量(t)")
    scrap_temp_c: float = Field(default=25.0, ge=0, description="废钢温度")
    
    # Targets
    target_temp_c: float = Field(default=1650.0, ge=0, description="目标出钢温度")
    target_c_pct: float = Field(default=0.05, ge=0, description="目标碳含量")

def calculate_thermal_balance(inp: ThermalBalanceInputs) -> CoolantRecommendation:
    """
    Danieli SDM Thermal Balance Calculation
    Based on: (Input Heat) + (Generated Heat) - (Consumed Heat) - (Lost Heat) = (Molten Steel and Slag Heat)
    """
    notes: List[str] = []

    # 1. Input Heat (Hot Metal)
    # hhm = CSPhm * Thm + hhm0
    h_hm = C_SP_HM * inp.iron_temp_c + H_HM_0
    H_hm_total = h_hm * inp.hot_metal_weight_t
    
    # 2. Input Heat (Scrap)
    # Hsc = Cspsc * (Tsc - 25) * Wsc (Danieli Formula)
    # Using Tsc directly if > 25, else 0 or negative (cooling)
    H_sc_total = C_SP_SC * (inp.scrap_temp_c - 25.0) * inp.scrap_weight_t
    
    # 3. Generated Heat (Reactions)
    # Calculate reacted masses (assuming 100% efficiency for now or standard removal)
    # Delta_C = Input_C - Target_C
    delta_c_pct = max(0, inp.c_content_pct - inp.target_c_pct)
    delta_si_pct = max(0, inp.si_content_pct - 0.0) # Assume 100% Si removal
    delta_mn_pct = max(0, inp.mn_content_pct - 0.1) # Assume residual Mn 0.1%
    delta_p_pct = max(0, inp.p_content_pct - 0.015) # Assume residual P 0.015%
    
    w_c_reacted = inp.hot_metal_weight_t * (delta_c_pct / 100.0)
    w_si_reacted = inp.hot_metal_weight_t * (delta_si_pct / 100.0)
    w_mn_reacted = inp.hot_metal_weight_t * (delta_mn_pct / 100.0)
    w_p_reacted = inp.hot_metal_weight_t * (delta_p_pct / 100.0)
    w_fe_reacted = inp.hot_metal_weight_t * 0.01 # Assume 1% Fe loss to slag
    
    # Carbon Oxidation Ratio (CO vs CO2)
    # PCO2 = 10% (Assume 90% CO, 10% CO2 standard)
    p_co2 = 0.10
    h_c_avg = H_R_C_CO * (1 - p_co2) + H_R_C_CO2 * p_co2
    
    H_reac_c = h_c_avg * w_c_reacted
    H_reac_si = H_R_SI * w_si_reacted
    H_reac_mn = H_R_MN * w_mn_reacted
    H_reac_p = H_R_P * w_p_reacted
    H_reac_fe = H_R_FE * w_fe_reacted
    
    H_reac_total = H_reac_c + H_reac_si + H_reac_mn + H_reac_p + H_reac_fe
    
    # 4. Heat Loss
    # Ladle Transfer Loss (Danieli: Phm_trns * sqrt(t) - ...)
    # Simplified: 1.5 * sqrt(waiting_time) per ton? No, temp drop.
    # Danieli: DeltaThm_trns = 1.5 * sqrt(waiting_time)
    temp_drop_transport = 1.5 * (inp.waiting_time_min ** 0.5)
    H_loss_transport = temp_drop_transport * C_SP_HM * inp.hot_metal_weight_t
    
    # Radiation Loss (Assume constant for now)
    H_loss_rad = 2000.0 # MJ (Estimate for 100t furnace)
    
    H_loss_total = H_loss_transport + H_loss_rad
    
    # 5. Output Heat Required (Steel + Slag)
    # Target: Steel at target_temp_c
    # Slag at target_temp_c (Usually slightly higher, but assume equal for balance)
    
    w_steel = inp.hot_metal_weight_t + inp.scrap_weight_t - (w_c_reacted + w_si_reacted + w_mn_reacted + w_p_reacted + w_fe_reacted)
    # Slag weight estimate (SiO2 * 2.5 roughly)
    w_sio2 = w_si_reacted * (60.08 / 28.09)
    w_slag = w_sio2 * 3.0 # Basic slag estimate
    
    h_st_target = C_SP_ST * inp.target_temp_c + H_ST_0
    H_st_required = h_st_target * w_steel
    
    h_slag_target = C_SP_SLAG * inp.target_temp_c # Approx enthalpy of slag
    H_slag_required = h_slag_target * w_slag
    
    H_out_required = H_st_required + H_slag_required
    
    # 6. Balance
    # Available = Input + Generated - Loss
    H_available = H_hm_total + H_sc_total + H_reac_total - H_loss_total
    
    # Surplus = Available - Required
    H_surplus = H_available - H_out_required
    
    # 7. Coolant Recommendation
    kg_per_t_coolant = 0.0
    coolant_type = CoolantType.qiufan
    
    if H_surplus > 0:
        # Need cooling
        # Cooling effect of coolant (e.g. scrap/ore)
        # Assume using Scrap/Return Fines (Qiufan) as coolant
        # Cooling = H_st_required_per_t - H_coolant_input
        # But simpler: Enthalpy difference between cold coolant and hot steel
        # H_cool_eff = (C_SP_ST * TargetT + H_ST_0) - (C_SP_SC * 25)
        h_cool_eff = (C_SP_ST * inp.target_temp_c + H_ST_0) - (C_SP_SC * 25.0)
        
        needed_coolant_t = H_surplus / h_cool_eff
        kg_per_t_coolant = (needed_coolant_t * 1000.0) / w_steel
        
        notes.append(f"热平衡盈余: {H_surplus:.1f} MJ")
        notes.append(f"建议冷却剂: {kg_per_t_coolant:.1f} kg/t")
    else:
        # Need heating (or less scrap)
        notes.append(f"热平衡亏损: {abs(H_surplus):.1f} MJ")
        notes.append("建议减少废钢或增加补热")
        kg_per_t_coolant = 0.0
    
    # Specific logic for One-Can / Si content
    if inp.is_one_can:
         notes.append("一罐到底模式：注意入炉温降修正")

    if inp.si_content_pct < 0.22:
        coolant_type = CoolantType.qizhaqiu
        notes.append("低硅铁水：优先弃渣球")
    else:
        coolant_type = CoolantType.qiufan
        notes.append("高硅铁水：优先球返")

    return CoolantRecommendation(
        coolant_type=coolant_type,
        kg_per_t=round(kg_per_t_coolant, 1),
        add_within_minutes=2.5,
        notes=notes,
    )
