from __future__ import annotations

from ..schemas import CriticalTempResult


def predict_critical_temp(*, v_content_pct: float | None = None, current_temp_c: float | None = None) -> CriticalTempResult:
    base = 1361.0

    if v_content_pct is None:
        t_critical = base
        notes = ["未提供熔池钒含量，按 1361℃ 基准估算。"]
    else:
        t_critical = base + (v_content_pct - 0.12) * 80.0
        notes = ["临界温度随熔池钒含量变化做线性微调（可在现场标定系数）。"]

    margin = None
    if current_temp_c is not None:
        margin = round(current_temp_c - t_critical, 2)
        notes.append("margin_c = T - T_critical，>0 表示已超过临界温度。")

    return CriticalTempResult(
        t_critical_c=round(t_critical, 2),
        current_temp_c=current_temp_c,
        margin_c=margin,
        notes=notes,
    )

