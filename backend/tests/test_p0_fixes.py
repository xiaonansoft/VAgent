# -*- coding: utf-8 -*-
"""P0 缺陷修复回归 —— 2026-10-02

覆盖五处造假/静默缺陷的修复：
1. list_conflicts 不再把「知识包缺失」伪装成「零冲突」（显式 degraded + missing 清单）
2. resolve_parameters 厂级包缺失不再崩溃（显式降级为行业基线单层 + RESOLVE_STATUS）
3. ValidationControlWriter 影子模式写调用诚实拒绝（ControlWriteRefused，绝不假装成功）
4. /api/system/mode await（静态检查 main.py 源码）
5. /api/heat/confirm learned_entries 不再返回 mock 常量（静态检查 main.py 源码）

可直接运行:  python3 tests/test_p0_fixes.py
或 pytest:   pytest tests/test_p0_fixes.py -v
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools import list_conflicts, query_knowledge_pack  # noqa: E402
from app.tools.plant_a_pack import last_resolve_status, resolve_parameters  # noqa: E402
from app.core.mode_control import ControlWriteRefused, ValidationControlWriter  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


def test_resolve_parameters_with_existing_plant():
    print("[1] plant_b 包存在 → 正常双层合并，不降级")
    params = resolve_parameters("plant_b")
    st = last_resolve_status()
    check("返回合并参数非空", isinstance(params, dict) and len(params) > 0)
    check("plant_pack_loaded=True", st["plant_pack_loaded"] is True)
    check("degraded=False", st["degraded"] is False)


def test_resolve_parameters_missing_pack_degrades():
    print("[2] 不存在的厂级包 → 不崩溃，显式降级为行业基线")
    params = resolve_parameters("plant_nonexistent")
    st = last_resolve_status()
    check("不崩溃且返回行业基线参数", isinstance(params, dict) and len(params) > 0)
    check("degraded=True", st["degraded"] is True, str(st))
    check("message 说明降级", "降级" in st["message"])


def test_list_conflicts_reports_missing_not_zero():
    print("[3] list_conflicts：plant_a 包缺失必须显式上报，而非静默零冲突")
    r = list_conflicts()
    check("degraded=True（存在缺失层）", r["degraded"] is True)
    check("missing 清单含 plant_a", "plant_a" in r["meta"]["missing_packs"])
    check("note 提示包缺失", "缺失" in r["note"])
    check("行业层冲突可见（known_conflict_count>0）",
          r["known_conflict_count"] > 0, f"got {r['known_conflict_count']}")
    check("packs 报告含三层", {p["pack"] for p in r["packs"]} >= {"industry", "plant_a"})


def test_query_knowledge_pack_degraded_flag():
    print("[4] query_knowledge_pack：缺失厂级包时返回体带 degraded 标记")
    r = query_knowledge_pack("", plant="plant_nonexistent")
    check("degraded=True", r.get("degraded") is True)
    check("degraded_note 非空", bool(r.get("degraded_note")))
    r2 = query_knowledge_pack("", plant="plant_b")
    check("plant_b 正常 → degraded=False", r2.get("degraded") is False)


def test_validation_writer_refuses():
    print("[5] ValidationControlWriter：四方法全部拒绝且留审计，绝不 return True")

    async def _run():
        w = ValidationControlWriter()
        refused = 0
        for call in (lambda: w.set_lance_height(1500.0),
                     lambda: w.set_oxygen_flow(250.0),
                     lambda: w.add_coolant("pellet", 300.0),
                     lambda: w.emergency_stop()):
            try:
                await call()
            except ControlWriteRefused:
                refused += 1
        return refused, len(w.logs)

    refused, logs = asyncio.run(_run())
    check("4 次调用全部 ControlWriteRefused", refused == 4, f"refused={refused}")
    check("审计日志 4 条", logs == 4, f"logs={logs}")


def test_main_endpoint_honesty():
    print("[6] main.py：switch_mode 已 await；learned_entries 不再是 mock 常量")
    src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py"),
               encoding="utf-8").read()
    check("switch_mode 已 await", "await mode_controller.switch_mode" in src)
    check("无 learned_entries mock 常量", "# Mock value" not in src)
    check("learned_entries 来自 DB 计数", "select(func.count()).select_from(Heat)" in src)


def test_production_writer_still_locked():
    print("[7] ProductionControlWriter 安全锁仍在（四方法 raise）")
    import inspect
    from app.core import mode_control as mc
    for m in ("set_lance_height", "set_oxygen_flow", "add_coolant", "emergency_stop"):
        src = inspect.getsource(getattr(mc.ProductionControlWriter, m))
        check(f"{m} 仍为 SAFETY LOCK", "NotImplementedError" in src)


if __name__ == "__main__":
    test_resolve_parameters_with_existing_plant()
    test_resolve_parameters_missing_pack_degrades()
    test_list_conflicts_reports_missing_not_zero()
    test_query_knowledge_pack_degraded_flag()
    test_validation_writer_refuses()
    test_main_endpoint_honesty()
    test_production_writer_still_locked()
    print("-" * 60)
    if FAILURES:
        print(f"✗ {len(FAILURES)} 项失败: {FAILURES}")
        sys.exit(1)
    print("✓ P0 修复回归全部通过")

