# -*- coding: utf-8 -*-
"""V 氧化热反演 (v_heat_calibration) —— GATE-2 数据外置版

对比两套 ΔH_V 假设（专家A Excel 2777 vs 仓库文献 15000）对同一批炉次实绩的
V2O5 品位预测误差，为 CF-001 仲裁提供证据。**系统只呈证据不代裁决。**

IP / GATE-2 纪律（2026-10-02 起）
--------------------------------
16 炉逐日生产实绩属保密数据，**严禁内联进任何代码或随仓库分发**：
- 真实数据外置于 `knowledge/data/private/plant_a_heats_16d.yaml`（.gitignore，本机自备，
  可从 Excel 原件或 git 历史恢复），或经环境变量 `VERO_HEATS_16D` 指定路径；
- 仓库仅内置合成演示数据 `knowledge/data/synthetic/heats_16d_synthetic.yaml`
  （逐行不同于任何真实炉次，显式标注"合成"，禁止作为效益基线）；
- `load_heats()` 在找不到真实数据时**报错并给出恢复指引，绝不静默回退到合成数据**
  ——把合成数据冒充实绩与"假装成功"是同一种造假。

用法
----
    python3 -m app.tools.v_heat_calibration               # 用真实数据（私有文件）
    python3 -m app.tools.v_heat_calibration --synthetic   # 用合成演示数据（显式标注）
    from app.tools.v_heat_calibration import load_heats, run_inversion
    verdict = run_inversion(load_heats(path="...")[0])
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

from . import plant_a_reference as pr

SCENARIOS: Dict[str, float] = {
    "A: 专家AExcel 2777 kJ/kg": 2777.0,
    "B: 仓库文献 15000 kJ/kg": 15000.0,
}

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
PRIVATE_HEATS = os.environ.get(
    "VERO_HEATS_16D",
    os.path.join(_REPO_ROOT, "knowledge", "data", "private", "plant_a_heats_16d.yaml"))
SYNTHETIC_HEATS = os.path.join(
    _REPO_ROOT, "knowledge", "data", "synthetic", "heats_16d_synthetic.yaml")


def load_heats(path: Optional[str] = None, synthetic: bool = False) -> Tuple[List[Dict], str]:
    """加载炉次实绩数据，返回 (heats, source_label)。

    查找顺序：显式 path → (synthetic=True 时) 仓库合成数据 → 环境变量/私有文件。
    找不到真实数据时抛 FileNotFoundError 并给恢复指引（不静默回退合成数据）。
    """
    import yaml

    if synthetic:
        target, label = SYNTHETIC_HEATS, "合成演示数据（非任何厂实绩）"
    elif path:
        target, label = path, f"外部数据 ({path})"
    else:
        target, label = PRIVATE_HEATS, "私有实绩数据（本机，未入库）"

    if not os.path.exists(target):
        if synthetic:
            raise FileNotFoundError(f"合成数据文件缺失: {target}（仓库应自带，请检查）")
        raise FileNotFoundError(
            "未找到 16 炉实绩数据文件。恢复方式任选其一：\n"
            f"  1. 将实绩数据放到 {target}（该路径已被 .gitignore，不会入库）\n"
            "  2. 设环境变量 VERO_HEATS_16D=<yaml路径>\n"
            "  3. 从 git 历史(≤commit 0be1e43)或专家A Excel 原件恢复\n"
            "  4. 仅需演示/冒烟时显式加 --synthetic（输出将标注合成数据）")
    with open(target, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    heats = doc.get("heats") or []
    if not heats:
        raise ValueError(f"数据文件无 heats 记录: {target}")
    if "合成" in str(doc.get("source", "")) and not synthetic and not path:
        label = f"{doc.get('source')}"  # 数据文件自带合成标注时如实呈现
    return heats, label


def predict_all(dh_v: float, heats: List[Dict]) -> List[float]:
    pr.DH_V = dh_v          # 热量平衡在调用时读取模块常量, 可安全切换
    return [pr.predict_v2o5_grade(4.3, h["si"], h["v"]) for h in heats]


def stats(errors: List[float]) -> Dict[str, float]:
    n = len(errors)
    rmse = (sum(e * e for e in errors) / n) ** 0.5
    mae = sum(abs(e) for e in errors) / n
    bias = sum(errors) / n
    return {"rmse": rmse, "mae": mae, "bias": bias, "n": n}


def run_inversion(heats: List[Dict]) -> Dict:
    """对给定炉次实绩跑双 ΔH 假设反演，返回逐目标 RMSE/MAE/偏差（供仲裁证据用）。"""
    preds = {name: predict_all(dh, heats) for name, dh in SCENARIOS.items()}
    verdict: Dict[tuple, Dict[str, float]] = {}
    for target in ("rough", "fine"):
        for name, ps in preds.items():
            errs = [p - h[target] for p, h in zip(ps, heats) if h[target] is not None]
            verdict[(name, target)] = stats(errs)
    return {"predictions": preds, "verdict": verdict}


def _excel_note_check(heats: List[Dict]) -> Optional[float]:
    """口径校验: 9-16日均值 Si 0.188 / V 0.297 → 专家模型应约 13.68%（Excel 备注口径）。

    仅对真实实绩数据有意义（合成数据无 Excel 备注对应物）。
    """
    tail = [h for h in heats if h["day"] >= 9]
    if len(tail) < 8:
        return None
    si = sum(h["si"] for h in tail) / len(tail)
    v = sum(h["v"] for h in tail) / len(tail)
    if abs(si - 0.188) > 0.005 or abs(v - 0.297) > 0.005:
        return None  # 非原口径数据，跳过校验
    pr.DH_V = 2777.0
    return pr.predict_v2o5_grade(4.3, si, v)


def main(argv: Optional[List[str]] = None) -> int:
    synthetic = "--synthetic" in (argv if argv is not None else sys.argv[1:])
    heats, label = load_heats(synthetic=synthetic)
    inv = run_inversion(heats)
    preds, verdict = inv["predictions"], inv["verdict"]

    print("=" * 88)
    print(f"V 氧化热反演 · 数据来源: {label} · n={len(heats)} 炉")
    if synthetic:
        print("⚠️  以下结果基于合成数据，仅验证流程，不构成 CF-001 仲裁证据")
    print("=" * 88)

    header = f"{'日':>3} {'Si%':>6} {'V%':>6} {'粗渣':>6} {'精渣':>6}"
    for name in SCENARIOS:
        header += f" {name[:11]:>12}"
    print(header)
    print("-" * 88)
    for i, h in enumerate(heats):
        row = (f"{h['day']:>3} {h['si']:>6.3f} {h['v']:>6.3f} "
               f"{h['rough'] or 0:>6.2f} {h['fine']:>6.2f}")
        for name in SCENARIOS:
            row += f" {preds[name][i]:>12.2f}"
        print(row)

    print("-" * 88)
    for target, tgt_label in (("rough", "粗钒渣装车样"), ("fine", "精钒渣")):
        print(f"\n◆ 对照 {tgt_label}品位:")
        for name in SCENARIOS:
            s = verdict[(name, target)]
            print(f"  {name:<24} RMSE={s['rmse']:.3f}  MAE={s['mae']:.3f}  "
                  f"偏差={s['bias']:+.3f}  (n={s['n']})")

    print("\n结论 (供专家仲裁, 非自动裁决):")
    for target, tgt_label in (("rough", "粗渣"), ("fine", "精渣")):
        best = min(SCENARIOS, key=lambda n: verdict[(n, target)]["rmse"])
        others = [n for n in SCENARIOS if n != best]
        print(f"  · 对照{tgt_label}: RMSE 更小的是 [{best}] "
              f"({verdict[(best, target)]['rmse']:.3f} vs "
              f"{verdict[(others[0], target)]['rmse']:.3f})")

    if not synthetic:
        check = _excel_note_check(heats)
        if check is not None:
            print(f"\n口径校验: 9-16日均值条件 (Si 0.188/V 0.297) → 本模型 {check:.2f}% "
                  f"(Excel 备注 13.68%)")
    print("\n注: 单一 ΔH 不足以解释全部偏差 (铁水C/温度/冷却制度逐炉不同),")
    print("    建议专家结合本表按炉次复核, 仲裁结果写入知识包 approved_by 字段。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
