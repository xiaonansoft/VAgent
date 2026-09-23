# -*- coding: utf-8 -*-
"""V 氧化热历史炉次反演 (V Heat Calibration)

问题: 攀钢 Excel 取 ΔH_V = 2777 kJ/kg (热量!E18), 仓库 MODEL_ALGORITHM.md
取 15000 MJ/t (≈热力学 V2O5 生成焓)。两者差 5.4 倍, 直接影响热量富余 →
冷料配吃量 → 渣稀释程度 → 钒渣品位。

方法: 用 Excel 工作表1 的 16 天生产实绩 (铁水 Si/V + 粗/精钒渣品位) 作为
历史证据, 分别按两个 ΔH 值预测品位, 比较 RMSE —— 让数据说话, 供专家仲裁。

运行: python3 -m app.tools.v_heat_calibration
"""

from typing import Dict, List

from app.tools import pangang_reference as pr

# --- 历史数据 (源: Excel 工作表"钒渣钒品位情况" B3:Q6, 日期1-16) ---
# (铁水Si%, 铁水V%, 粗钒渣装车样V2O5%, 精钒渣V2O5%); None=Excel缺样
HEATS: List[Dict] = [
    {"day": 1,  "si": 0.19,  "v": 0.319, "rough": 14.47, "fine": 14.06},
    {"day": 2,  "si": 0.152, "v": 0.325, "rough": 14.41, "fine": 13.25},
    {"day": 3,  "si": 0.154, "v": 0.323, "rough": 15.11, "fine": 13.59},
    {"day": 4,  "si": 0.14,  "v": 0.329, "rough": 14.05, "fine": 13.67},
    {"day": 5,  "si": 0.172, "v": 0.332, "rough": 14.17, "fine": 13.64},
    {"day": 6,  "si": 0.142, "v": 0.33,  "rough": 15.85, "fine": 13.91},
    {"day": 7,  "si": 0.138, "v": 0.333, "rough": 14.59, "fine": 14.24},
    {"day": 8,  "si": 0.135, "v": 0.319, "rough": None,  "fine": 14.19},
    {"day": 9,  "si": 0.128, "v": 0.331, "rough": 14.68, "fine": 14.59},
    {"day": 10, "si": 0.125, "v": 0.298, "rough": 14.92, "fine": 13.9},
    {"day": 11, "si": 0.195, "v": 0.294, "rough": 13.41, "fine": 13.28},
    {"day": 12, "si": 0.192, "v": 0.284, "rough": 14.03, "fine": 13.21},
    {"day": 13, "si": 0.144, "v": 0.286, "rough": 13.06, "fine": 12.72},
    {"day": 14, "si": 0.266, "v": 0.299, "rough": 12.24, "fine": 13.59},
    {"day": 15, "si": 0.251, "v": 0.287, "rough": 13.48, "fine": 14.7},
    {"day": 16, "si": 0.13,  "v": 0.288, "rough": 14.27, "fine": 12.61},
]

SCENARIOS = {
    "A: 攀钢Excel 2777 kJ/kg": 2777.0,
    "B: 仓库文献 15000 kJ/kg": 15000.0,
}


def predict_all(dh_v: float) -> List[float]:
    pr.DH_V = dh_v          # 热量平衡在调用时读取模块常量, 可安全切换
    return [pr.predict_v2o5_grade(4.3, h["si"], h["v"]) for h in HEATS]


def stats(errors: List[float]) -> Dict[str, float]:
    n = len(errors)
    rmse = (sum(e * e for e in errors) / n) ** 0.5
    mae = sum(abs(e) for e in errors) / n
    bias = sum(errors) / n
    return {"rmse": rmse, "mae": mae, "bias": bias}


def main() -> None:
    print("=" * 88)
    print("V 氧化热反演: 16 炉次实绩 (源: 工作表'钒渣钒品位情况') × 两套 ΔH 假设")
    print("=" * 88)

    results = {name: predict_all(v) for name, v in SCENARIOS.items()}

    header = f"{'日':>3} {'Si%':>6} {'V%':>6} {'粗渣':>6} {'精渣':>6}"
    for name in SCENARIOS:
        header += f" {name[:11]:>12}"
    print(header)
    print("-" * 88)
    for i, h in enumerate(HEATS):
        row = (f"{h['day']:>3} {h['si']:>6.3f} {h['v']:>6.3f} "
               f"{h['rough'] or 0:>6.2f} {h['fine']:>6.2f}")
        for name in SCENARIOS:
            row += f" {results[name][i]:>12.2f}"
        print(row)

    print("-" * 88)
    verdict = {}
    for target, label in (("rough", "粗钒渣装车样"), ("fine", "精钒渣")):
        print(f"\n◆ 对照 {label}品位:")
        for name, preds in results.items():
            errs = [p - h[target] for p, h in zip(preds, HEATS) if h[target] is not None]
            s = stats(errs)
            verdict[(name, target)] = s["rmse"]
            print(f"  {name:<24} RMSE={s['rmse']:.3f}  MAE={s['mae']:.3f}  "
                  f"偏差={s['bias']:+.3f}  (n={len(errs)})")

    print("\n结论 (供专家仲裁, 非自动裁决):")
    for target, label in (("rough", "粗渣"), ("fine", "精渣")):
        best = min(SCENARIOS, key=lambda n: verdict[(n, target)])
        print(f"  · 对照{label}: RMSE 更小的是 [{best}] "
              f"({verdict[(best, target)]:.3f} vs "
              f"{verdict[((list(SCENARIOS)[1 - list(SCENARIOS).index(best)]), target)]:.3f})")

    # 与 Excel 备注的口径校验: 9-16日均值 Si 0.188 / V 0.297 → 专家模型 13.68%
    pr.DH_V = 2777.0
    check = pr.predict_v2o5_grade(4.3, 0.188, 0.297)
    print(f"\n口径校验: 9-16日均值条件 (Si 0.188/V 0.297) → 本模型 {check:.2f}% "
          f"(Excel 备注 13.68%)")
    print("注: 单一 ΔH 不足以解释全部偏差 (铁水C/温度/冷却制度逐炉不同),")
    print("    建议专家结合本表按炉次复核, 仲裁结果写入知识包 approved_by 字段。")


if __name__ == "__main__":
    main()
