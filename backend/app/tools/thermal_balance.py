from __future__ import annotations

from pydantic import BaseModel, Field

from ..schemas import CoolantRecommendation, CoolantType


class ThermalBalanceInputs(BaseModel):
    iron_temp_c: float = Field(..., ge=0)
    si_content_pct: float = Field(..., ge=0)
    is_one_can: bool


def calculate_thermal_balance(inp: ThermalBalanceInputs) -> CoolantRecommendation:
    base_temp_c = 1280.0
    delta = max(0.0, inp.iron_temp_c - base_temp_c)

    kg_per_t = 8.0 + delta * 0.6

    notes: list[str] = []

    if inp.is_one_can:
        kg_per_t += 10.0
        notes.append("一罐到底：入炉物理热较高，冷却剂基准量上调约 10 kg/t。")

    if inp.si_content_pct < 0.22:
        coolant_type = CoolantType.qizhaqiu
        notes.append("低硅铁水：优先弃渣球（成本优先）。")
    else:
        coolant_type = CoolantType.qiufan
        kg_per_t *= 1.5
        notes.append("高硅铁水：优先球返（强冷却），冷却剂按基准约 1.5 倍。")

    notes.append("必须在开吹后 2.5 分钟内加完，避免喷溅或返干风险。")

    return CoolantRecommendation(
        coolant_type=coolant_type,
        kg_per_t=round(kg_per_t, 1),
        add_within_minutes=2.5,
        notes=notes,
    )
