# -*- coding: utf-8 -*-
"""VERO 物理内核（physics）—— 冶炼物理的单一实现

职责边界（域 1/4）：只回答"熔池在怎么演化"，不做任何决策、不产生建议、不管呈现。

本模块从 `session.py` 原样迁移而来，**算法逐字未改**。迁移目的是解耦，不是重写：
- 迁移前后必须通过 `test_physics_parity.py` 的逐点双跑对比（与旧实现比对）
- 任何对本文件的修改都必须先跑双跑门禁

红线：本模块纯计算，无副作用、无 I/O、无执行通道。
"""

from __future__ import annotations

from typing import List

from ..tools.kinetics_simulator import calculate_kinetics_derivatives
from ..tools.critical_temp import predict_critical_temp

# ---- 常量（自 session.py 迁移；已消解 Q_COOL_KJ_KG 重复定义）----
TC_C = 1361.0            # 碳钒转化温度基准（industry 包 CF-007；实际随 V 动态修正）
TARGET_V = 0.03          # 半钢残钒目标 %
V_BLOW_LINE = 0.04       # 补吹线（余钒 >0.04% 须补吹）
Q_COOL_KJ_KG = 1500.0    # 冷料有效吸热·演示标定（原 session.py 中重复定义两次，值同；此处保留唯一一处）
CP_BATH = 0.8            # kJ/(kg·℃)
DEMO_KV_SCALE = 2.5      # 演示标定旋钮（待 ≥50 炉真实标定后替换）
DEMO_KC_SCALE = 0.10
COOL_WIN = (60.0, 240.0)  # 计划冷料投入窗口（模拟秒）

# 状态向量布局（8 维，勿改——积分与序列化均依赖此顺序）
IDX_C, IDX_SI, IDX_V, IDX_MN, IDX_T, IDX_O, IDX_FEO, IDX_LOSS = range(8)


def derivs(state: List[float], t_s: float, bath_kg: float, o2_nm3_h: float,
           lance_mm: float) -> List[float]:
    """状态对时间的导数。薄封装：注入 k 标定旋钮。"""
    mols_o2_s = (o2_nm3_h / 3600.0) / 0.0224
    return calculate_kinetics_derivatives(state, t_s, bath_kg, mols_o2_s,
                                          lance_height_mm=lance_mm,
                                          k_v_scale=DEMO_KV_SCALE,
                                          k_c_scale=DEMO_KC_SCALE)


def tc(v_pct: float) -> float:
    """动态碳钒转化温度：Tc = 1361 + (V-0.12)×80（单一来源 tools/critical_temp.py）。"""
    try:
        return float(predict_critical_temp(v_content_pct=v_pct).t_critical_c)
    except Exception:
        return TC_C


def lance_plan(t_min: float, base: float = 1100.0) -> float:
    """方案枪位曲线（低-高-低）。"""
    if t_min < 1.0:
        return base
    if t_min < 5.0:
        return base + 100.0
    return base - 100.0


def integrate(state: List[float], t0_s: float, dt_s: float, bath_kg: float,
              o2_nm3_h: float, lance_fn, substep_s: float = 1.0,
              cool_rate_c_s: float = 0.0) -> None:
    """Euler 推进（就地修改），dt_s 内按 substep_s 分步。

    cool_rate_c_s：计划冷料折算的持续降温速率（℃/模拟秒），仅在 COOL_WIN 窗口内生效。
    数值强制 python float——numpy 标量无法被 json 序列化（SSE 曾因此静默断流）。
    """
    remaining = dt_s
    while remaining > 1e-9:
        h = min(substep_s, remaining)
        t_abs = t0_s + h
        d = derivs(state, t_abs, bath_kg, o2_nm3_h, lance_fn(t_abs / 60.0))
        cool = cool_rate_c_s if COOL_WIN[0] <= t_abs <= COOL_WIN[1] else 0.0
        state[0] = max(0.01, float(state[0] + d[0] * h))
        state[1] = max(0.005, float(state[1] + d[1] * h))
        state[2] = max(0.001, float(state[2] + d[2] * h))
        state[3] = max(0.001, float(state[3] + d[3] * h))
        state[4] = max(1000.0, min(2000.0, float(state[4] + d[4] * h - cool * h)))
        state[5] = max(0.0, float(state[5] + d[5] * h))
        state[6] = max(0.0, float(state[6] + d[6] * h))
        state[7] = max(0.0, float(state[7] + d[7] * h))
        remaining -= h
