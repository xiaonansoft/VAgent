from __future__ import annotations

from ..schemas import LanceMode, LanceProfile, LanceStep


def recommend_lance_profile(*, si_content_pct: float) -> LanceProfile:
    if si_content_pct > 0.2:
        steps = [LanceStep(start_min=0.0, end_min=6.0, lance_height_mm=950)]
        mode = LanceMode.constant_low
    else:
        steps = [
            LanceStep(start_min=0.0, end_min=2.0, lance_height_mm=950),
            LanceStep(start_min=2.0, end_min=5.0, lance_height_mm=1100),
            LanceStep(start_min=5.0, end_min=6.0, lance_height_mm=950),
        ]
        mode = LanceMode.low_high_low

    return LanceProfile(
        mode=mode,
        steps=steps,
        endgame_action="终点前30秒压枪至900mm，以降低渣中TFe含量。",
    )

