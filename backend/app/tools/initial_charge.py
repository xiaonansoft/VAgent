from __future__ import annotations

from ..schemas import InitialChargeInputs, InitialChargeResult
from ..core.config import settings


def calculate_initial_charge(inp: InitialChargeInputs) -> InitialChargeResult:
    """
    L1 静态模型 (SDM): 基于达涅利四大平衡与现场实战规则计算开吹配料。
    """
    # 1. 物理热计算 (Q_in)
    # 铁水比热容 Cp ~ 0.8 kJ/(kg*K)
    cp_hm = settings.cp_hm
    
    # 精细化热损耗模型 (Ref: Danieli SDM)
    # T_loss = k1 * sqrt(t_transport) + k2 * sqrt(t_empty)
    # 经验系数 (假设值，需现场标定): k1=2.5, k2=3.0
    k1, k2 = 2.5, 3.0
    t_loss_transport = k1 * (inp.ladle_transport_time_min ** 0.5)
    t_loss_empty = k2 * (inp.ladle_empty_time_min ** 0.5)
    total_temp_loss = t_loss_transport + t_loss_empty
    
    # 实际入炉温度
    t_actual_in = inp.iron_temp_c - total_temp_loss
    
    # 一罐到底修正：若采用一罐到底，铁水有效温度增加 30℃ (相当于热补偿)
    t_eff = t_actual_in + (settings.one_can_temp_boost if inp.is_one_can else 0.0)
    
    q_in = inp.iron_weight_t * 1000 * cp_hm * t_eff

    # 2. 反应热计算 (Q_react)
    # 基于标准生成焓：Si -> SiO2 (27620 kJ/kg), V -> V2O3 (~15200 kJ/kg), C -> CO (9280 kJ/kg)
    # 提钒终点残 V 目标通常为 0.03%
    delta_si = inp.iron_analysis.Si / 100.0
    delta_v = max(0.0, (inp.iron_analysis.V - settings.target_v_residual) / 100.0)
    # 碳氧化仅计算氧化到 3.5% 部分的热量 (提钒过程碳不完全氧化)
    delta_c = max(0.0, (inp.iron_analysis.C - settings.target_c_oxidation_start) / 100.0)

    q_si = inp.iron_weight_t * 1000 * delta_si * settings.h_si_oxidation
    q_v = inp.iron_weight_t * 1000 * delta_v * settings.h_v_oxidation
    q_c = inp.iron_weight_t * 1000 * delta_c * settings.h_c_oxidation
    q_react = q_si + q_v + q_c

    # 3. 目标热需求 (Q_out)
    # 目标终点温度下的物理热，考虑 5% 的散热损失
    q_target = inp.iron_weight_t * 1000 * 0.85 * inp.target_temp_c
    q_loss = q_target * settings.heat_loss_ratio

    # 4. 热盈余与冷却剂计算 (Q_coolant)
    q_excess = (q_in + q_react) - (q_target + q_loss)

    warnings = []
    recipe = {}

    # V/(Si+Ti) 富集判据
    si_ti_sum = inp.iron_analysis.Si + inp.iron_analysis.Ti
    ratio = inp.iron_analysis.V / si_ti_sum if si_ti_sum > 0 else 99.0
    
    if ratio < 1.05:
        warnings.append("V/(Si+Ti) 比值偏低: 极难富集。强制增加氧化铁皮/高钒块矿，禁止使用弃渣球。")
        # 氧化铁皮吸热能力约 2000 kJ/kg
        oxide_scale_t = max(0.0, q_excess / (settings.h_oxide_scale_absorption * 1000))
        recipe["氧化铁皮"] = round(oxide_scale_t, 2)
    else:
        # 如果热盈余为负，说明入炉温度过低（可能是热损耗过大）
        if q_excess < 0:
            warnings.append(f"警告：热量不足 (缺口 {abs(q_excess/1000):.1f} MJ)。建议减少废钢，增加铁水温度或使用化学热补偿。")
            recipe["提温剂(FeSi)"] = round(abs(q_excess) / (25000 * 1000), 2) # 硅铁发热值 ~25MJ/kg
        
        elif inp.iron_analysis.Si > 0.25:
            warnings.append("高硅铁水: 强制使用生铁块以降低喷溅风险。")
            # 生铁块吸热能力约 1200 kJ/kg
            pig_iron_t = max(0.0, q_excess / (settings.h_pig_iron_absorption * 1000))
            recipe["生铁块"] = round(pig_iron_t, 2)
        else:
            # 默认使用生铁块
            pig_iron_t = max(0.0, q_excess / (settings.h_pig_iron_absorption * 1000))
            recipe["生铁块"] = round(pig_iron_t, 2)

    # 5. 渣量预测
    # 渣量公式: 2.14 * delta_Si + 1.79 * delta_V
    w_slag = settings.slag_coeff_si * (inp.iron_weight_t * 1000 * delta_si) + settings.slag_coeff_v * (inp.iron_weight_t * 1000 * delta_v)
    w_slag_t = w_slag / 1000.0
    
    if inp.is_one_can:
        w_slag_t *= 1.1
        warnings.append("一罐到底工艺: 已按规则增加 10% 预计渣量（模拟高炉渣混入）。")

    # 6. 总氧量估算 (m3)
    # Si: 0.8, V: 0.5, C: 0.93 (m3/kg)
    oxy_si = (inp.iron_weight_t * 1000 * delta_si) * settings.oxy_coeff_si
    oxy_v = (inp.iron_weight_t * 1000 * delta_v) * settings.oxy_coeff_v
    oxy_c = (inp.iron_weight_t * 1000 * delta_c) * settings.oxy_coeff_c
    oxygen_total = oxy_si + oxy_v + oxy_c

    return InitialChargeResult(
        recipe=recipe,
        oxygen_total_m3=round(oxygen_total, 1),
        slag_weight_t=round(w_slag_t, 2),
        v_si_ti_ratio=round(ratio, 3),
        warnings=warnings,
    )
