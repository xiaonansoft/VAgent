from __future__ import annotations

from ..schemas import InitialChargeInputs, InitialChargeResult
from .pangang_pack import resolve_parameters


def _get(node, *path):
    """按路径取值: _get(P['l1_charge'], 'target_temp_c', 'value')"""
    for key in path:
        node = node[key]
    return node


def calculate_initial_charge(inp: InitialChargeInputs) -> InitialChargeResult:
    """
    L1 静态模型 (提钒冶炼 行业通用逻辑 + 厂级参数覆盖): 基于建龙现场工艺规程查表法
    计算开吹配料与冷却剂策略。参考: 黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf
    参数由 resolve_parameters() 按「行业基线(industry) → 厂级包(默认 jianlong)」合并,
    单一事实来源: 冷却剂查表/氧量/渣量系数为厂级参数, V/(Si+Ti) 判据为行业基线。
    """

    P = resolve_parameters()
    l1 = P["l1_charge"]
    dist = P["coolant_distribution"]
    oxy = P["oxygen"]
    slag = P["slag"]

    # --- 1. 基础热计算 (用于校验) ---
    # 仍保留基础物理热计算作为底座，但主要逻辑转向建龙查表法

    # 目标: 半钢温度 1360-1400 (Target 1380)
    target_temp = _get(l1, "target_temp_c", "value")

    # --- 2. 冷却剂计算 (建龙查表法) ---
    # 规则:
    # 基准: 铁水温度 1280 vs 1300, Si 分档
    # 铁水温度每上升 10度, 冷却剂增加 1.8 kg/t
    # Si +/- 0.01%, 温度 +/- 4.78度 -> 换算冷却剂

    # 基础冷却剂消耗 (kg/t) - 基于 1300 度表 (线性插值)
    si = inp.iron_analysis.Si
    temp = inp.iron_temp_c
    temp_base = _get(l1, "temp_base_c", "value")

    # --- Memory Correction (CheckpointSaver) ---
    if inp.prev_lining_heat:
        # 1 单位炉衬蓄热 ≈ 0.5 度等效升温
        correction = inp.prev_lining_heat * _get(l1, "lining_heat_correction_c_per_unit", "value")
        temp += correction
        # Note: We modify local 'temp' variable used for coolant calculation,
        # but not the original input record.

    lookup = l1["coolant_lookup_kg_t"]
    base_coolant_kg_t = 0.0

    # 1300度基准表 (取中间值)
    if si <= 0.15:
        base_coolant_kg_t = _get(lookup, "si_le_015", "value")
    elif 0.15 < si <= 0.20:
        base_coolant_kg_t = _get(lookup, "si_015_020", "value")
    elif 0.20 < si <= 0.25:
        base_coolant_kg_t = _get(lookup, "si_020_025", "value")
    else:  # > 0.25
        base_coolant_kg_t = _get(lookup, "si_gt_025", "value")

    # 温度修正 (基准 1300)
    temp_diff = temp - temp_base
    # +10度 -> +1.8 kg/t => 0.18 kg/t/deg
    temp_correction = temp_diff * _get(l1, "temp_correction_kg_t_per_c", "value")

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
    # 优先级: 钒渣铁 > 氧化铁皮 > 球返/球团
    recipe = {}
    warnings = []

    vsi = dist["v_slag_iron"]
    scale = dist["scale"]

    # 钒渣铁 (Vanadium Slag Iron): 循环利用, 铁水Si高时使用 (>0.20%)
    v_slag_iron_t = 0.0
    if si >= _get(vsi, "si_threshold", "value"):
        v_slag_iron_t = min(_get(vsi, "cap_t", "value"), total_coolant_weight_t * _get(vsi, "share", "value"))
        recipe["钒渣铁"] = round(v_slag_iron_t, 2)
        total_coolant_weight_t -= v_slag_iron_t
        warnings.append("高硅铁水(>=0.20%): 已启用钒渣铁(废钢斗加入)。")

    # 氧化铁皮 (Scale): 兑铁后下枪前加入
    scale_t = 0.0
    if total_coolant_weight_t > 0:
        scale_t = min(_get(scale, "cap_t", "value"), total_coolant_weight_t * _get(scale, "share", "value"))
        recipe["氧化铁皮"] = round(scale_t, 2)
        total_coolant_weight_t -= scale_t

    # 球返/球团 (Pellets/Returns): 主力冷却剂
    pellets_t = max(0.0, total_coolant_weight_t)
    recipe["球返/球团"] = round(pellets_t, 2)

    # 警告检查
    pellet_cap = _get(dist, "pellet_cap_t", "value")
    if pellets_t > pellet_cap:
        warnings.append(f"警告: 球返加入量 ({pellets_t:.2f}t) 超过 {pellet_cap}t 限制，建议检查铁水温度或增加废钢/生铁。")

    # --- 4. 氧量计算 ---
    # 供氧量 20000-21000 Nm3/h
    # 吹炼时间 5-6 min
    # 精细化: 根据成分
    delta_si = si / 100.0
    delta_c = (inp.iron_analysis.C - _get(oxy, "target_c_pct", "value")) / 100.0
    delta_v = (inp.iron_analysis.V - _get(oxy, "target_v_pct", "value")) / 100.0
    delta_ti = inp.iron_analysis.Ti / 100.0
    delta_mn = (inp.iron_analysis.P - _get(oxy, "target_p_pct", "value")) / 100.0  # Mn 氧化部分(现状误用 P)

    oxy_demand = (
        (delta_si * _get(oxy, "coeff_si_m3_kg", "value")) +
        (delta_c * _get(oxy, "coeff_c_m3_kg", "value")) +
        (delta_v * _get(oxy, "coeff_v_m3_kg", "value")) +
        (delta_ti * _get(oxy, "coeff_ti_m3_kg", "value"))
    ) * inp.iron_weight_t * 1000

    # 效率修正
    oxygen_total = oxy_demand / _get(oxy, "efficiency", "value")

    # --- 5. 渣量预测 ---
    sio2 = (delta_si * inp.iron_weight_t * 1000) * _get(slag, "coeff_sio2", "value")
    v2o3 = (delta_v * inp.iron_weight_t * 1000) * _get(slag, "coeff_v2o3", "value")
    tio2 = (delta_ti * inp.iron_weight_t * 1000) * _get(slag, "coeff_tio2", "value")

    # 冷却剂带入的杂质 (球团 SiO2 ~5%)
    coolant_sio2 = (pellets_t + v_slag_iron_t) * 1000 * _get(slag, "coolant_sio2_share", "value")

    total_slag = sio2 + v2o3 + tio2 + coolant_sio2
    # FeO + MnO + Others ~ 40% of slag
    total_slag /= _get(slag, "non_ferrous_divisor", "value")

    slag_t = total_slag / 1000.0

    # V/(Si+Ti) check
    si_ti_sum = inp.iron_analysis.Si + inp.iron_analysis.Ti
    ratio = inp.iron_analysis.V / si_ti_sum if si_ti_sum > 0 else 99.0
    if ratio < _get(P, "quality", "v_si_ti_ratio_min", "value"):
        warnings.append("V/(Si+Ti) < 1.0: 渣品位可能不达标。")

    return InitialChargeResult(
        recipe=recipe,
        oxygen_total_m3=round(oxygen_total, 1),
        slag_weight_t=round(slag_t, 2),
        v_si_ti_ratio=round(ratio, 3),
        warnings=warnings
    )
