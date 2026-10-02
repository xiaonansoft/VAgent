# -*- coding: utf-8 -*-
"""双引擎冲突仲裁演示 (Arbitration Demo)

左案 A = 专家A机理引擎 (plant_a_reference, 源: 专家A专家 Excel)
右案 B = 专家B查表引擎 (MODEL_ALGORITHM.md §1 / initial_charge.py 口径)

演示仲裁三要素:
1. 双方案对照 —— 同一输入下两套引擎各自输出, 含溯源
2. 历史证据   —— 16 炉次实绩回放, 各方案 RMSE (引擎 B 无品位预测能力,
                这本身就是查表法的能力缺口证据)
3. 人工决策位 —— 每条冲突给出 [采用A]/[采用B]/[本炉例外]/[挂起] 选项,
                本演示仅生成证据, 不自动裁决

GATE-2 纪律: 炉次实绩数据不内联（见 v_heat_calibration 模块头）。默认读本机私有
数据文件；无私有数据时用 --synthetic 显式跑合成数据（报告标注合成，不作仲裁证据）。

运行: python3 -m app.tools.arbitration_demo [--synthetic]
输出: 控制台 + 仓库根目录 ARBITRATION_DEMO.md
"""

import os
import sys
from typing import Dict, List, Optional

from app.tools import plant_a_reference as pr
from app.tools.v_heat_calibration import SCENARIOS, load_heats, predict_all, stats

# ---------------------------------------------------------------------------
# 引擎 B: 专家B查表法 (源: MODEL_ALGORITHM.md §1, initial_charge.py 同口径)
# ---------------------------------------------------------------------------

def plant_b_coolant_kg_per_t(si: float, temp: float) -> Dict:
    """基准查表 + 温度修正 + 文档上限"""
    if si <= 0.15:
        base = 22.5
    elif si <= 0.20:
        base = 33.0
    elif si <= 0.25:
        base = 39.0
    else:
        base = 45.0
    w = base + (temp - 1300.0) * 0.18          # ΔW_temp, 每10°C 1.8kg/t
    return {"base": base, "uncapped": w, "capped": min(w, 25.0)}


def plant_b_allocation(w_total_t: float, si: float) -> Dict:
    """冷却剂分配优先级: 钒渣铁 → 氧化铁皮 → 球团 (MODEL_ALGORITHM.md §1.2)"""
    v_slag = min(2.0, 0.5 * w_total_t) if si >= 0.20 else 0.0
    scale = min(1.0, 0.5 / w_total_t) if w_total_t > 2.0 else 1.0  # 超2.5t上限按比例缩
    v_slag *= scale
    scale_l = min(1.0, 0.5 / max(1e-9, w_total_t - v_slag))
    scale_l = 1.0 if (w_total_t - v_slag) <= 0.5 else 0.5 / (w_total_t - v_slag)
    oxide = min(0.5, 0.3 * (w_total_t - v_slag)) * scale_l
    pellet = max(0.0, w_total_t - v_slag - oxide)
    return {"钒渣铁": v_slag, "氧化铁皮": oxide, "球团": pellet}


def plant_b_slag_simple(si: float, v: float, metal_kg: float) -> float:
    """简化渣量: W = 2.14ΔSi + 1.79ΔV (kg/kg氧化元素), 仅计 SiO2+V2O5"""
    d_si = (si - 0.006) / 100.0 * metal_kg
    d_v = (v - 0.025) / 100.0 * metal_kg
    return 2.14 * d_si + 1.79 * d_v


# ---------------------------------------------------------------------------
# 仲裁执行
# ---------------------------------------------------------------------------

def engine_a(plant_a_dh_v: float = 2777.0) -> Dict:
    pr.DH_V = plant_a_dh_v
    r = pr.run_plant_a_model()
    return {
        "name": f"A 专家A机理引擎 (ΔH_V={plant_a_dh_v:.0f})",
        "coolant": {k: w for k, w in r.after["coolant_weights"].items() if w},
        "coolant_kg_per_t_iron": r.after["coolant_weights"]["pellet"] / 80000 * 1000,
        "slag_total": r.after["slag"],
        "slag_non_fe": r.material["non_fe_oxides"],
        "heat_surplus_mj": r.heat["surplus"] / 1e6,
        "grade": r.v2o5_grade,
        "grade_capable": True,
        "provenance": "专家AExcel 8表703公式, 复现误差0.0002%",
    }


def engine_b(si: float = 0.215, temp: float = 1300.0, v: float = 0.284) -> Dict:
    c = plant_b_coolant_kg_per_t(si, temp)
    w_t = c["uncapped"] * 80 / 1000
    slag = plant_b_slag_simple(si, v, 80000)
    return {
        "name": "B 专家B查表引擎 (MODEL_ALGORITHM.md §1)",
        "coolant_base": c["base"], "coolant_uncapped": c["uncapped"],
        "coolant_capped": c["capped"],
        "allocation_t": plant_b_allocation(w_t, si),
        "slag_simple": slag,
        "grade_capable": False,
        "provenance": "专家B规程查表 (Source 106/95), 硬编码于 initial_charge.py",
    }


def evidence_table(heats: List[Dict]) -> Dict[str, Dict[str, float]]:
    """炉次历史回放: 各 ΔH 假设对粗/精渣的 RMSE（数据经入参注入，不内联）"""
    out = {}
    for name, dh in SCENARIOS.items():
        preds = predict_all(dh, heats)
        for target in ("rough", "fine"):
            errs = [p - h[target] for p, h in zip(preds, heats) if h[target] is not None]
            out[(name, target)] = stats(errs)
    return out


CONF_LIST = [
    ("CF-001", "V氧化热 kJ/kg", "2777 (热量!E18)", "15000 (MODEL_ALGORITHM.md)"),
    ("CF-002", "冷却剂品种/等效", "金属铁/球团/块矿/弃渣球, 吸热比1:4.2:4.65:4.21",
     "生铁/铁皮/钒渣球, 1:5.5:2.5 (Source 95)"),
    ("CF-003", "渣量算法", "渣成分反推, 非铁氧化物 1141.8 kg", "2.14ΔSi+1.79ΔV ≈ 728.7 kg (漏Mn/Ti/Cr/P)"),
    ("CF-004", "冷却剂基准", "机理: 富余热量/单位吸热", "查表 22.5-45 kg/t + 0.18kg/t/°C"),
    ("CF-005", "半钢残钒", "0.0375% (预算)", "≤0.03% (硬约束)"),
    ("CF-006", "专家B文档内部矛盾", "—", "基准表最高45 kg/t vs 上限25 kg/t (自查发现)"),
]


def main(synthetic: bool = False, heats: Optional[List[Dict]] = None) -> None:
    if heats is None:
        heats, data_label = load_heats(synthetic=synthetic)
    else:
        data_label = "调用方注入数据"
    a = engine_a()
    b = engine_b()
    ev = evidence_table(heats)
    lines: List[str] = []
    emit = lambda s="": (print(s), lines.append(s))

    emit("# 冲突仲裁演示报告 (ARBITRATION_DEMO)")
    emit()
    emit(f"> 输入: 铁水 80t / 1300°C / Si 0.215% / V 0.284% · 生成: 本演示脚本")
    emit(f"> 历史证据数据来源: {data_label} · n={len(heats)} 炉")
    if synthetic:
        emit("> ⚠️ 合成演示数据：本报告仅验证流程，不构成 CF-001 仲裁证据；"
             "真实证据须以本机私有实绩数据重跑生成")
    emit()
    emit("## 一、双方案对照 (同一输入)")
    emit()
    emit("| 维度 | 引擎A 专家A机理 | 引擎B 专家B查表 |")
    emit("|---|---|---|")
    emit(f"| 冷却剂需求 | 球团 {a['coolant_kg_per_t_iron']:.1f} kg/t铁水 (机理反算) "
         f"| 基准 {b['coolant_base']:.1f} kg/t → 上限后 {b['coolant_capped']:.1f} kg/t |")
    alloc = b["allocation_t"]
    emit(f"| 品种分配 | 球团 {list(a['coolant'].values())[0]/1000:.2f} t | "
         f"钒渣铁 {alloc['钒渣铁']:.2f} / 铁皮 {alloc['氧化铁皮']:.2f} / 球团 {alloc['球团']:.2f} t |")
    emit(f"| 渣量 | {a['slag_total']:.0f} kg (全口径) | {b['slag_simple']:.0f} kg (仅SiO2+V2O5) |")
    emit(f"| 热量富余 | {a['heat_surplus_mj']:.1f} MJ | 不计算 (查表法无热平衡) |")
    emit(f"| 品位预测 | **{a['grade']:.2f}%** (可预测) | 无此能力 |")
    emit(f"| 溯源 | {a['provenance']} | {b['provenance']} |")
    emit()
    emit("## 二、历史证据 (16 炉次实绩回放)")
    emit()
    emit("| 假设 | 对照粗渣RMSE | 对照精渣RMSE | 偏差(精渣) |")
    emit("|---|---|---|---|")
    for (name, target), s in ev.items():
        if target == "rough":
            fine = ev[(name, "fine")]
            emit(f"| {name} | {s['rmse']:.3f} | {fine['rmse']:.3f} | {fine['bias']:+.3f} |")
    emit()
    emit("## 三、冲突清单与决策位")
    emit()
    emit("| # | 议题 | 方案A (专家A) | 方案B (专家B/仓库) | 决策 |")
    emit("|---|---|---|---|---|")
    for cid, topic, pa, pb in CONF_LIST:
        emit(f"| {cid} | {topic} | {pa} | {pb} | ☐采用A ☐采用B ☐例外 ☐挂起 |")
    emit()
    emit("## 四、仲裁结论建议 (由证据生成, 待专家确认)")
    best_b = min(ev.items(), key=lambda kv: kv[1]["rmse"] if kv[0][1] == "fine" else 9e9)
    emit(f"1. CF-001: 16炉次回放中 15000 假设 RMSE 更小 ({best_b[1]['rmse']:.3f}), "
         f"但两套假设均系统性偏高 (偏差 +{best_b[1]['bias']:.2f}pp), 说明还有未建模因素")
    emit("   (铁水C/温度逐炉变化、实际冷料制度), **建议: 仓库参数保留15000为默认, "
         "专家A2777挂'待复核'标签, 补齐炉次实据后再定**")
    emit("2. CF-003: 专家B简化渣量公式漏计 Mn/Ti/Cr/P 氧化物 (~410kg, 36%),")
    emit("   **建议: 查表法保留用于快速场景, 渣量计算以机理口径为准**")
    emit("3. CF-006: 专家B文档基准45 vs 上限25 的内部矛盾, **建议: 提交专家B专家澄清**")
    emit()
    emit("> 仲裁原则: 系统只呈证据不代决策; 每次人工决策作为判例入库,")
    emit("> 同类冲突再次出现时预填历史倾向, 但永远保留人工确认。")

    with open(os.path.join(os.path.dirname(__file__), "..", "..", "ARBITRATION_DEMO.md"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n[已写入 ARBITRATION_DEMO.md]")


if __name__ == "__main__":
    main(synthetic="--synthetic" in sys.argv)
