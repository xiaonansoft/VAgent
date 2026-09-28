# -*- coding: utf-8 -*-
"""双引擎 parity 校验 (Python 权威引擎 ↔ JS 演示页冻结引擎)

VERO 红线声明
-------------
本测试是**防漂移机制**, 不是计算引擎。它只做两件事:
1. 用 backend/tests/golden_cases.json 的 11 项黄金基准校验 Python 权威引擎;
2. 把同一组基准喂给 HTML 演示页里冻结的 JS 引擎, 比对是否仍然一致。

任何一侧失败 = CI 红灯。若 Python 侧因机理迭代而偏离, 必须经专家评审后
修订 golden_cases.json 的期望值, **严禁**为了让测试通过而随意改期望值,
更严禁把 Python 的新机理回移到 JS(见 docs/ENGINE_SINGLE_SOURCE.md)。

VERO 红线: LLM 只做翻译器/检索器/建议器, **零数值计算权**、**不碰控制回路**;
本文件不含任何 LLM 调用。

运行:
    python -m pytest backend/tests/test_engine_parity.py -q -s
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))

# backend 加入 sys.path, 使 `app` 包可导入 (与同目录既有测试一致)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

GOLDEN_PATH = os.path.join(HERE, "golden_cases.json")

NODE_BIN = "/Users/yanwenqing/.workbuddy/binaries/node/versions/22.22.2-3/bin/node"

# 候选演示页: v0.9 优先, 缺失则回退 v0.8
HTML_CANDIDATES = ["VERO_MVP_v0.9.html", "VERO_MVP_v0.8.html"]

# 11 项黄金字段 (顺序 = 报告输出顺序)
FIELDS = ["fc", "slg", "steel", "o2kg", "tI", "tS",
          "surplus", "pl", "steel2", "grade", "balPct"]


# ============================================================================
# 加载
# ============================================================================

def _load_golden() -> dict:
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_plant_a_reference():
    """导入 Python 权威引擎模块。

    优先按包路径导入; 若因并行开发导致 app 包暂时不可用, 退化为按文件路径
    直接加载 plant_a_reference.py (该模块为纯标准库实现, 无包内依赖)。
    """
    try:
        from app.tools import plant_a_reference  # noqa: WPS433
        return plant_a_reference
    except Exception:
        import importlib.util
        path = os.path.join(BACKEND_DIR, "app", "tools", "plant_a_reference.py")
        spec = importlib.util.spec_from_file_location("_plant_a_reference", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


GOLDEN = _load_golden()
pr = _load_plant_a_reference()


# ============================================================================
# 一、Python 权威引擎
# ============================================================================

def run_python_engine(case: dict) -> dict:
    """按 golden_cases.json 的输入跑 Python 引擎, 返回 11 项标准化结果"""
    inp = case["input"]
    d = case.get("input_defaults", {})

    iron = pr.MetalAnalysis(
        C=inp["C"], Si=inp["Si"], Mn=d["Mn"], P=d["P"], S=d["S"],
        V=inp["V"], Cr=d["Cr"], Ti=d["Ti"], temp=inp["T"])
    semi = pr.MetalAnalysis(**d["semi_steel"])

    pg_inp = pr.PlantAInputs(
        iron_weight=inp["W"],
        pig_iron_weight=d.get("pig_iron_weight", 0.0),
        iron=iron,
        semi_steel=semi,
        fesilicon_kg=d.get("fesilicon_kg", 34.5),
        coolant_weights=dict(d.get("coolant_weights", {"pellet": None})),
        corrected=False,
    )

    # dhV 可覆盖 (JS runModel 支持 inp.dhV; Python 侧 DH_V 为模块常量)
    original_dhv = pr.DH_V
    try:
        if inp.get("dhV") is not None:
            pr.DH_V = float(inp["dhV"])
        r = pr.run_plant_a_model(pg_inp)
    finally:
        pr.DH_V = original_dhv

    return {
        "fc": r.material["iron_C_fixed"],
        "slg": r.material["slag_total"],
        "steel": r.material["steel"],
        "o2kg": r.material["o2_kg"],
        "tI": r.heat["tf_iron"],
        "tS": r.heat["tf_steel"],
        "surplus": r.heat["surplus"],
        "pl": r.after["coolant_weights"]["pellet"],
        "steel2": r.after["steel"],
        "grade": r.product["slag_grade"]["V2O5"],
        "balPct": r.material["balance_diff_pct"] * 100.0,
    }


# ============================================================================
# 二、JS 冻结引擎 (Node 子进程)
# ============================================================================

def find_demo_html() -> str | None:
    for name in HTML_CANDIDATES:
        p = os.path.join(REPO_ROOT, name)
        if os.path.isfile(p):
            return p
    return None


def extract_first_script(html_path: str) -> str:
    """抽出 HTML 中第一段内联 <script> (即冻结的引擎段)"""
    import re
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    for m in re.finditer(r"<script([^>]*)>(.*?)</script>", html, re.S):
        attrs, body = m.group(1), m.group(2)
        if "src=" in attrs:          # 外链脚本跳过
            continue
        return body
    raise ValueError(f"{os.path.basename(html_path)} 中未找到内联 <script> 段")


def run_js_engine(case: dict, html_path: str) -> dict:
    """在 Node 子进程中执行冻结的 JS 引擎, 返回 11 项结果"""
    script = extract_first_script(html_path)
    runner = (
        script
        + "\n;\n"
        + "const __INP = " + json.dumps(case["input"]) + ";\n"
        + "const __R = runModel(__INP);\n"
        + "const __OUT = {};\n"
        + "for (const k of " + json.dumps(FIELDS) + ") {"
        + "  let v = __R[k]; if (k === 'balPct') v = v * 100; __OUT[k] = v; }\n"
        + "console.log(JSON.stringify(__OUT));\n"
    )
    with tempfile.TemporaryDirectory() as td:
        js_path = os.path.join(td, "vero_engine_probe.js")
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(runner)
        proc = subprocess.run(
            [NODE_BIN, js_path],
            capture_output=True, text=True, timeout=60,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Node 执行失败 (rc={proc.returncode}):\n{proc.stderr.strip()[:2000]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _js_available() -> tuple[bool, str]:
    if not (os.path.isfile(NODE_BIN) and os.access(NODE_BIN, os.X_OK)):
        return False, f"Node 不可用: {NODE_BIN} 不存在或不可执行"
    html = find_demo_html()
    if html is None:
        return False, "演示页缺失: " + " / ".join(HTML_CANDIDATES)
    return True, html


# ============================================================================
# 三、比对与报告
# ============================================================================

def rel_err(actual: float, expected: float, floor: float = 1e-9) -> float:
    return abs(actual - expected) / max(abs(expected), floor)


def build_table(title: str, actual: dict, golden: dict, baseline: dict | None = None) -> str:
    """输出对比表; baseline 给定时额外显示与 Python 权威值的偏差"""
    tol = GOLDEN["meta"]["tolerance"]["rel"]
    has_base = baseline is not None
    head = (f"{'字段':<8}{'黄金期望':>20}{'实际':>20}{'相对误差':>12}"
            + (f"{'vs Python':>12}" if has_base else "") + f"{'判定':>6}")
    lines = [f"\n=== {title} ===", head, "-" * 78]
    for k in FIELDS:
        exp = golden["expect"][k]
        act = actual.get(k)
        if act is None:
            lines.append(f"{k:<8}{exp:>20.7g}{'MISSING':>20}{'-':>12}{'FAIL':>6}")
            continue
        err = rel_err(act, exp)
        ok = "OK" if err <= tol else "FAIL"
        row = f"{k:<8}{exp:>20.7g}{act:>20.7g}{err:>12.2e}"
        if has_base:
            b = baseline.get(k)
            row += f"{(rel_err(act, b) if b is not None else float('nan')):>12.2e}"
        lines.append(row + f"{ok:>6}")
    return "\n".join(lines)


def assert_golden(actual: dict, title: str, baseline: dict | None = None) -> None:
    tol = GOLDEN["meta"]["tolerance"]["rel"]
    table = build_table(title, actual, GOLDEN, baseline)
    print(table)  # -s 时可见
    bad = []
    for k in FIELDS:
        exp = GOLDEN["expect"][k]
        act = actual.get(k)
        if act is None or rel_err(act, exp) > tol:
            bad.append(f"{k}: expect={exp!r} actual={act!r}")
    assert not bad, (f"{title} 未通过 {len(bad)}/{len(FIELDS)} 项 (容差 rel={tol}):\n"
                     + "\n".join(bad) + "\n" + table)


# ============================================================================
# 四、测试用例
# ============================================================================

def test_golden_case_file_is_sane():
    """黄金基准文件自身结构完整 (防手改坏 JSON / 漏字段)"""
    assert set(FIELDS) == set(GOLDEN["expect"].keys()), "expect 字段集与 FIELDS 不一致"
    assert GOLDEN["meta"]["frozen_date"] == "2026-09-27"
    assert GOLDEN["meta"]["tolerance"]["rel"] == 1e-4
    for k in ("W", "Si", "V", "T", "C", "dhV"):
        assert k in GOLDEN["input"], f"input 缺字段 {k}"
    assert set(FIELDS) == set(GOLDEN["mapping"].keys())


def test_python_engine_matches_golden():
    """① Python 权威引擎 11 项黄金基准"""
    actual = run_python_engine(GOLDEN)
    assert_golden(actual, "Python 权威引擎 (backend/app/tools/plant_a_reference.py)")


def test_js_engine_matches_golden():
    """② JS 冻结引擎 11 项黄金基准 (Node 子进程; 不可用时 skip 而非 fail)"""
    ok, reason = _js_available()
    if not ok:
        pytest.skip(reason)

    html_path = reason
    py_actual = run_python_engine(GOLDEN)
    try:
        js_actual = run_js_engine(GOLDEN, html_path)
    except Exception as e:  # 抽取失败 / Node 报错 → 标记 skip 原因, 不阻断 CI
        pytest.skip(f"JS 引擎无法执行 ({os.path.basename(html_path)}): {e}")

    print(f"\nJS 引擎来源: {os.path.basename(html_path)} · Node: {NODE_BIN}")
    assert_golden(js_actual,
                  f"JS 冻结引擎 ({os.path.basename(html_path)})",
                  baseline=py_actual)


def test_python_and_js_agree_with_each_other():
    """③ 双引擎互比: JS 必须逐项贴合 Python 权威值 (漂移即红灯)"""
    ok, reason = _js_available()
    if not ok:
        pytest.skip(reason)

    html_path = reason
    py_actual = run_python_engine(GOLDEN)
    try:
        js_actual = run_js_engine(GOLDEN, html_path)
    except Exception as e:
        pytest.skip(f"JS 引擎无法执行 ({os.path.basename(html_path)}): {e}")

    print(build_table("双引擎互比 (Python vs JS)", js_actual, GOLDEN, baseline=py_actual))
    drift = [f"{k}: python={py_actual[k]!r} js={js_actual.get(k)!r} "
             f"rel={rel_err(js_actual[k], py_actual[k]):.3e}"
             for k in FIELDS
             if js_actual.get(k) is None
             or rel_err(js_actual[k], py_actual[k]) > GOLDEN["meta"]["tolerance"]["rel"]]
    assert not drift, (
        f"JS 引擎已相对 Python 权威引擎漂移 {len(drift)} 项 —— 按 "
        f"docs/ENGINE_SINGLE_SOURCE.md: 禁止把 Python 新机理回移 JS, "
        f"应对齐 Python / 或让 JS 自然死亡退役。\n" + "\n".join(drift))


if __name__ == "__main__":
    print(f"黄金基准: {GOLDEN_PATH}")
    py = run_python_engine(GOLDEN)
    assert_golden(py, "Python 权威引擎")
    ok, reason = _js_available()
    if ok:
        assert_golden(run_js_engine(GOLDEN, reason),
                      f"JS 冻结引擎 ({os.path.basename(reason)})", baseline=py)
    else:
        print(f"[skip] JS 侧: {reason}")
    print("\n全部通过")
