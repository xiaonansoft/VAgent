from __future__ import annotations

from ..schemas import LanceMode, LanceProfile, LanceStep
from .plant_a_pack import resolve_parameters


def _get(node, *path):
    for key in path:
        node = node[key]
    return node


def recommend_lance_profile(*, si_content_pct: float) -> LanceProfile:
    """
    提钒冶炼 行业通用枪位控制 (多方文献一致, 非某厂专属):
      · 标准模式「低-高-低」: 点火/前期低枪位 → 主吹高枪位(软吹化渣、保碳)
        → 终点压枪低枪位(降渣中 FeO)。
      · 高 Si: 枪位保持下限(全程低枪位), 抑制脱碳、保钒。
    依据: 专家A综述「枪位 低→高→低」、铁水预处理提钒讲课稿「低—高—低」、
          黑龙江专家B p22「Si<0.2% 低-高-低 / Si>0.2% 全过程低枪位」、
          下钢(苏联)综述「高硅时整个冶炼期枪位保持下限」。
    模式逻辑取自行业基线(industry), 阈值(0.2%)与枪位值(900/1200mm)为厂级默认参数,
    由 resolve_parameters() 按「行业基线 → 厂级覆盖」合并得到, 可被厂级包覆盖。
    """

    P = resolve_parameters()
    lp = P["lance_profile"]

    threshold = _get(lp, "si_threshold_pct", "value")
    low = _get(lp, "low_lance_mm", "value")
    high = _get(lp, "high_lance_mm", "value")
    timing = lp["low_high_low_timing"]
    low_until = _get(timing, "low_until_min", "value")
    end_press_s = _get(timing, "end_press_s", "value")
    total = _get(timing, "total_blow_min", "value")

    if si_content_pct < threshold:
        # 低-高-低: 0~low_until 低 → 过程高 → 结束前 end_press_s 低
        end_press_start = total - end_press_s / 60.0
        steps = [
            LanceStep(start_min=0.0, end_min=low_until, lance_height_mm=int(low)),
            LanceStep(start_min=low_until, end_min=round(end_press_start, 3), lance_height_mm=int(high)),
            LanceStep(start_min=round(end_press_start, 3), end_min=total, lance_height_mm=int(low)),
        ]
        return LanceProfile(
            mode=LanceMode.low_high_low,
            steps=steps,
            endgame_action=f"吹氧结束前40秒压枪至{int(low)}mm，降低渣中FeO。",
        )

    # 高硅(≥阈值): 全过程低枪位(保持下限)
    return LanceProfile(
        mode=LanceMode.constant_low,
        steps=[LanceStep(start_min=0.0, end_min=total, lance_height_mm=int(low))],
        endgame_action=f"高硅(≥{threshold}%)吹炼全过程保持低枪位{int(low)}mm，抑制脱碳、保钒。",
    )
