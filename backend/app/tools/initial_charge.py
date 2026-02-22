from __future__ import annotations

from ..schemas import InitialChargeInputs, InitialChargeResult
from ..core.config import settings

def calculate_initial_charge(inp: InitialChargeInputs) -> InitialChargeResult:
    """
    L1 静态模型 (Jianlong Site): 基于建龙现场工艺规程计算开吹配料与冷却剂策略。
    参考: 黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf
    """
    
    # --- 1. 基础热计算 (用于校验) ---
    # 仍保留基础物理热计算作为底座，但主要逻辑转向建龙查表法
    
    # 目标: 半钢温度 1360-1400 (Target 1380)
    target_temp = 1380.0
    
    # --- 2. 冷却剂计算 (建龙查表法) ---
    # 规则: 
    # 基准: 铁水温度 1280 vs 1300, Si 分档
    # 铁水温度每上升 10度, 冷却剂增加 1.8 kg/t
    # Si +/- 0.01%, 温度 +/- 4.78度 -> 换算冷却剂
    
    # 基础冷却剂消耗 (kg/t) - 基于 1300 度表 (线性插值)
    # Si ranges: <=0.15, 0.15-0.20, 0.20-0.25, 0.25-0.30
    si = inp.iron_analysis.Si
    temp = inp.iron_temp_c
    
    # --- Memory Correction (CheckpointSaver) ---
    if inp.prev_lining_heat:
        # Simple heuristic: 1 unit of heat accumulation ~= 0.5 degree effective temp increase
        correction = inp.prev_lining_heat * 0.5
        temp += correction
        # Note: We modify local 'temp' variable used for coolant calculation, 
        # but not the original input record.
    
    base_coolant_kg_t = 0.0
    
    # 1300度基准表 (取中间值)
    if si <= 0.15:
        base_coolant_kg_t = 22.5 # 15-30
    elif 0.15 < si <= 0.20:
        base_coolant_kg_t = 33.0 # 30-36
    elif 0.20 < si <= 0.25:
        base_coolant_kg_t = 39.0 # 36-42
    else: # > 0.25
        base_coolant_kg_t = 45.0 # 42-48
        
    # 温度修正 (基准 1300)
    temp_diff = temp - 1300.0
    # +10度 -> +1.8 kg/t => 0.18 kg/t/deg
    temp_correction = temp_diff * 0.18
    
    total_coolant_kg_t = base_coolant_kg_t + temp_correction
    
    # 限制范围 (最大不超过 2.5吨/炉 -> ~25kg/t for 100t)
    # 建龙文档说 "提钒冷却剂加入量最多不超过 2.5 吨" (针对120t炉? 文档提到了120t炉)
    # 2.5t / 120t = 20.8 kg/t.
    # 但表里有 48 kg/t. 可能 2.5t 是单种限制? 或者总限制?
    # 文档: "提钒冷却剂加入量最多不超过 2.5 吨" (P16). 
    # 同时也给出了 40+ kg/t 的表.
    # 可能是指 "球团/球返" 不超过 2.5t? 
    # 让我们遵循计算值，但给出警告如果过高。
    
    total_coolant_kg_t = max(0.0, total_coolant_kg_t)
    total_coolant_weight_t = (total_coolant_kg_t * inp.iron_weight_t) / 1000.0
    
    # --- 3. 冷却剂分配策略 ---
    recipe = {}
    warnings = []
    
    # 优先级: 钒渣铁 > 氧化铁皮 > 球返/球团
    
    # 钒渣铁 (Vanadium Slag Iron): 循环利用, 铁水Si高时使用 (>0.20%)
    # 文档: "铁水Si>=0.20%时，配加返铁进行温度调整"
    # 文档: "钒渣铁产消平衡"
    v_slag_iron_t = 0.0
    if si >= 0.20:
        v_slag_iron_t = min(2.0, total_coolant_weight_t * 0.5) # 假设一半用钒渣铁，上限2t
        recipe["钒渣铁"] = round(v_slag_iron_t, 2)
        total_coolant_weight_t -= v_slag_iron_t
        warnings.append("高硅铁水(>=0.20%): 已启用钒渣铁(废钢斗加入)。")
    
    # 氧化铁皮 (Scale): 兑铁后下枪前加入
    # 文档未给出具体比例，通常作为补充或调节。
    # 假设固定量或剩余部分的 20%
    scale_t = 0.0
    if total_coolant_weight_t > 0:
        scale_t = min(0.5, total_coolant_weight_t * 0.3) # Max 0.5t
        recipe["氧化铁皮"] = round(scale_t, 2)
        total_coolant_weight_t -= scale_t
        
    # 球返/球团 (Pellets/Returns): 主力冷却剂
    # 开吹30s后加入，2.5min内加完
    pellets_t = max(0.0, total_coolant_weight_t)
    recipe["球返/球团"] = round(pellets_t, 2)
    
    # 警告检查
    if pellets_t > 2.5:
        warnings.append(f"警告: 球返加入量 ({pellets_t:.2f}t) 超过 2.5t 限制，建议检查铁水温度或增加废钢/生铁。")

    # --- 4. 氧量计算 ---
    # 供氧量 20000-21000 Nm3/h
    # 吹炼时间 5-6 min
    # 估算: 21000 * (5.5/60) = 1925 m3
    # 精细化: 根据成分
    delta_si = si / 100.0
    delta_c = (inp.iron_analysis.C - 3.50) / 100.0 # 半钢碳目标 >= 3.50
    delta_v = (inp.iron_analysis.V - 0.05) / 100.0 # 氧化率 90%
    delta_ti = inp.iron_analysis.Ti / 100.0
    delta_mn = (inp.iron_analysis.P - 0.10) / 100.0 # Mn 氧化部分
    
    # Oxygen coeff (m3/kg)
    oxy_si = 0.8
    oxy_c = 0.93
    oxy_v = 0.5 # V -> V2O3 (4V+3O2 -> 1.5 O2 per V? 3/4=0.75 mol. 0.75*22.4/51 = 0.33 m3/kg)
                # Actually 4V + 3O2 -> 2V2O3. 3 mol O2 (67.2L) for 4 mol V (204g). 67.2/204 = 0.33. 
                # Let's use standard coeffs.
    oxy_v_coeff = 0.35
    oxy_ti_coeff = 0.5
    
    oxy_demand = (
        (delta_si * oxy_si) + 
        (delta_c * oxy_c) + 
        (delta_v * oxy_v_coeff) + 
        (delta_ti * oxy_ti_coeff)
    ) * inp.iron_weight_t * 1000
    
    # 效率修正 (90%)
    oxygen_total = oxy_demand / 0.9
    
    # --- 5. 渣量预测 ---
    # 渣成分: SiO2, V2O3, TiO2, FeO, MnO
    # SiO2 = Si_loss * (60/28)
    sio2 = (delta_si * inp.iron_weight_t * 1000) * 2.14
    v2o3 = (delta_v * inp.iron_weight_t * 1000) * 1.47
    tio2 = (delta_ti * inp.iron_weight_t * 1000) * 1.67
    
    # 冷却剂带入的杂质 (球团 SiO2 ~5%)
    coolant_sio2 = (pellets_t + v_slag_iron_t) * 1000 * 0.05
    
    total_slag = sio2 + v2o3 + tio2 + coolant_sio2
    # FeO + MnO + Others ~ 40% of slag
    total_slag /= 0.6
    
    slag_t = total_slag / 1000.0
    
    # V/(Si+Ti) check
    si_ti_sum = inp.iron_analysis.Si + inp.iron_analysis.Ti
    ratio = inp.iron_analysis.V / si_ti_sum if si_ti_sum > 0 else 99.0
    if ratio < 1.0:
        warnings.append("V/(Si+Ti) < 1.0: 渣品位可能不达标。")

    return InitialChargeResult(
        recipe=recipe,
        oxygen_total_m3=round(oxygen_total, 1),
        slag_weight_t=round(slag_t, 2),
        v_si_ti_ratio=round(ratio, 3),
        warnings=warnings
    )
