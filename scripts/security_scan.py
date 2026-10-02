#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VERO 安全扫描门禁（security_scan）—— 边界文档 §一「边界必须由技术强制」的 CI 落地

四项断言（全部通过才退出 0，任一失败退出 1 并列出证据）：
  [1] 控制写入锁：ProductionControlWriter 四方法体只允许 raise（SAFETY LOCK 完好）；
      ValidationControlWriter 四方法必须显式拒绝（含 ControlWriteRefused），禁止假装成功。
  [2] 工业协议禁入：backend/ 全量禁止 import opcua / pymodbus / snap7（只读边界，
      数据接入必须走 DATA_INTERFACE_SPEC 的 resource:// 适配层评审）。
  [3] 路由扫描：FastAPI 路由不得出现控制写入类端点（plc/dcs/actuator/write_control 等）。
  [4] 实绩指纹扫描：git 跟踪文件不得包含 16 炉真实生产实绩的特征值与内联模式
      （GATE-2；合成演示数据与文档口径讨论不受影响）。

运行: python3 scripts/security_scan.py          # 本地
     CI: .github/workflows/ci.yml 已接入
"""

import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  ✗ {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if f]


# ---------------------------------------------------------------------------
# [1] 控制写入锁
# ---------------------------------------------------------------------------

WRITE_METHODS = {"set_lance_height", "set_oxygen_flow", "add_coolant", "emergency_stop"}


def check_control_lock() -> None:
    print("[1] 控制写入锁（ProductionControlWriter=只许 raise；ValidationControlWriter=必须拒绝）")
    path = os.path.join(ROOT, "backend", "app", "core", "mode_control.py")
    tree = ast.parse(open(path, encoding="utf-8").read())

    classes: dict[str, ast.ClassDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node

    prod = classes.get("ProductionControlWriter")
    if prod is None:
        fail("ProductionControlWriter 类缺失")
        return
    for fn in ast.walk(prod):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name in WRITE_METHODS:
            body_stmts = [s for s in fn.body if not (
                isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
            all_raise = all(isinstance(s, ast.Raise) for s in body_stmts)
            if all_raise:
                ok(f"ProductionControlWriter.{fn.name} 仅含 raise（SAFETY LOCK）")
            else:
                fail(f"ProductionControlWriter.{fn.name} 方法体含非 raise 语句——安全锁被破坏！")

    val = classes.get("ValidationControlWriter")
    if val is None:
        fail("ValidationControlWriter 类缺失")
        return
    src = open(path, encoding="utf-8").read()
    if "ControlWriteRefused" not in src:
        fail("ValidationControlWriter 未显式拒绝（ControlWriteRefused 缺失）")
    for fn in ast.walk(val):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name in WRITE_METHODS:
            returns_true = any(
                isinstance(s, ast.Return) and isinstance(s.value, ast.Constant) and s.value.value is True
                for s in ast.walk(fn))
            if returns_true:
                fail(f"ValidationControlWriter.{fn.name} 存在 return True——假装成功回归！")
            else:
                ok(f"ValidationControlWriter.{fn.name} 无假装成功返回")


# ---------------------------------------------------------------------------
# [2] 工业协议禁入
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORTS = re.compile(r"^\s*(import|from)\s+(opcua|pymodbus|snap7)\b", re.M)


def check_forbidden_protocols() -> None:
    print("[2] 工业协议禁入（backend/ 禁止 opcua/pymodbus/snap7 直连）")
    backend = os.path.join(ROOT, "backend")
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(backend):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".venv", "venv")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            src = open(p, encoding="utf-8", errors="ignore").read()
            for m in FORBIDDEN_IMPORTS.finditer(src):
                hits.append(f"{os.path.relpath(p, ROOT)}: {m.group(0).strip()}")
    if hits:
        for h in hits:
            fail(f"发现被禁工业协议直连: {h}（须经 resource:// 适配层评审）")
    else:
        ok("backend/ 无 opcua/pymodbus/snap7 直连")


# ---------------------------------------------------------------------------
# [3] 路由扫描
# ---------------------------------------------------------------------------

FORBIDDEN_ROUTE = re.compile(r"(plc|dcs|actuator|write[_-]?control|control[_-]?write|send[_-]?command)", re.I)


def check_routes() -> None:
    print("[3] 路由扫描（FastAPI 端点不得含控制写入类路径）")
    path = os.path.join(ROOT, "backend", "app", "main.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    routes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr in ("get", "post", "put", "delete", "patch")):
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        routes.append(str(dec.args[0].value))
    bad = [r for r in routes if FORBIDDEN_ROUTE.search(r)]
    if bad:
        for r in bad:
            fail(f"路由疑似控制写入端点: {r}")
    else:
        ok(f"{len(routes)} 条路由扫描通过，无控制写入端点")


# ---------------------------------------------------------------------------
# [4] 实绩指纹扫描（GATE-2）
# ---------------------------------------------------------------------------

# 内联炉次数据模式（JS/JSON 风格 {day:1,si:...}，含引号键名与变体空格）
INLINE_HEATS = re.compile(r'["\']?day["\']?\s*:\s*\d+\s*,\s*["\']?si["\']?\s*:')
# 真实 16 炉特征值（精确字面量，re.escape；粗渣装车样 V2O5 与铁水 V 的稀有点位）
REAL_FINGERPRINTS = ["14.47", "15.11", "15.85", "0.319", "0.333"]
# 允许清单：文件名 → 理由（如确需在文档中讨论口径，须脱敏为区间或趋势表述）
ALLOWLIST: dict[str, str] = {
    # "docs/xxx.md": "口径讨论，已脱敏为区间",
}


def check_fingerprints() -> None:
    print("[4] 实绩指纹扫描（git 跟踪文件不得含 16 炉真实实绩）")
    hits: list[str] = []
    for f in tracked_files():
        if f in ALLOWLIST or f.startswith(("archive/",)):
            continue
        if not f.endswith((".py", ".md", ".html", ".js", ".ts", ".yaml", ".yml", ".json", ".css")):
            continue
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8", errors="ignore").read()
        real_vals = [v for v in REAL_FINGERPRINTS if re.search(re.escape(v), src)]
        # 形状命中只有在同时含真实特征值时才算泄露（合成演示数据同形状但零真实值）
        if INLINE_HEATS.search(src) and real_vals:
            hits.append(f"{f}: 内联炉次数据且含真实特征值 {real_vals}")
        if len(real_vals) >= 2:
            hits.append(f"{f}: 命中真实实绩特征值 {real_vals}")
        elif len(real_vals) == 1 and not INLINE_HEATS.search(src) and f.endswith((".py", ".html")):
            hits.append(f"{f}: 命中真实实绩特征值 {real_vals}（代码/页面文件单项命中也须人工复核）")
    if hits:
        for h in hits:
            fail(f"GATE-2 实绩泄露: {h}")
    else:
        ok("全部跟踪文件无实绩指纹（内联模式+真实值 / 特征值组合）")


def main() -> int:
    print("=" * 72)
    print("VERO 安全扫描门禁（边界由技术强制，不靠文档自觉）")
    print("=" * 72)
    check_control_lock()
    check_forbidden_protocols()
    check_routes()
    check_fingerprints()
    print("-" * 72)
    if FAILURES:
        print(f"✗ {len(FAILURES)} 项失败：")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("✓ 四项安全断言全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
