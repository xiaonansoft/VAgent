from __future__ import annotations

from ..schemas import LanceMode, LanceProfile, LanceStep


def recommend_lance_profile(*, si_content_pct: float) -> LanceProfile:
    """
    Jianlong Site Lance Profile (Low-High-Low)
    Ref: 黑龙江建龙转炉提钒技术材料--修改--2020.6.13(1).pdf
    
    Table Logic:
    Si < 0.15: Process 1.5m -> End 1.4m
    Si 0.15-0.30: Process 1.4m -> End 1.3m
    Si > 0.30: Process 1.3m -> End 1.3m
    
    Standard Operation:
    1. Ignition (Start): Low lance (1.2m, 30s) to ignite.
    2. Process (Main): High lance (Table value) to promote V oxidation and control Temp.
    3. End (Press): Low lance (Table value, >30s) to lower TFe in slag.
    """
    
    steps = []
    mode = LanceMode.low_high_low
    
    # 1. Ignition Step (Fixed for all)
    steps.append(LanceStep(start_min=0.0, end_min=0.5, lance_height_mm=1200))
    
    # 2. Process & End Steps (Based on Si)
    process_h = 1400 # Default
    end_h = 1300     # Default
    
    if si_content_pct < 0.15:
        process_h = 1500
        end_h = 1400
    elif 0.15 <= si_content_pct <= 0.30:
        process_h = 1400
        end_h = 1300
    else: # > 0.30
        process_h = 1300
        end_h = 1300
        
    # Main Process: 0.5 min to 5.5 min (Assume 6 min total blow)
    steps.append(LanceStep(start_min=0.5, end_min=5.5, lance_height_mm=process_h))
    
    # End Press: 5.5 min to 6.0 min (30s)
    steps.append(LanceStep(start_min=5.5, end_min=6.0, lance_height_mm=end_h))

    return LanceProfile(
        mode=mode,
        steps=steps,
        endgame_action=f"终点前30秒压枪至{end_h}mm，以降低渣中TFe含量。",
    )
