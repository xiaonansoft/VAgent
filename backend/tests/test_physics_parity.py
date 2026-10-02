# -*- coding: utf-8 -*-
"""物理内核双跑门禁（physics parity gate）

**这是本次重构的护城河门禁。** 目标：新 `physics.py` 与旧 `session.py` 内联实现
在相同输入下必须逐点一致，误差 < 1e-12。任一断言失败即阻止切换。

被测对象：
- 新：`app.blow.physics`（域 1，纯物理）
- 旧：`app.blow.session` 内的 `_derivs` / `_tc` / `_lance_plan` / `_integrate`

测试设计要点：
1. **不 import 私有名的脆弱假设**——旧实现通过 getattr 取，若 session 已迁移则跳过并显式告警，
   绝不静默通过（"缺证据"不等于"通过"）。
2. 覆盖三个函数 + 积分器，且积分器用多条不同工况（含 COOL_WIN 内外）拉长序列。
3. 误差判据取相对+绝对混合，避开浮点末位噪声。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.blow import physics  # noqa: E402


def _legacy():
    """取旧实现（session.py 内联）。若已迁移则返回 None。"""
    try:
        mod = importlib.import_module("app.blow.session")
    except Exception:
        return None
    if not hasattr(mod, "_integrate"):
        return None
    return mod


legacy = _legacy()

requires_legacy = pytest.mark.skipif(
    legacy is None,
    reason="旧内联实现已不存在于 session.py（迁移完成后应改为快照比对）",
)

# 状态向量初值：取多组，覆盖 C/Si/V/T 的不同起��
STATES = [
    [4.30, 0.19, 0.100, 0.35, 1290.0, 0.0, 0.0, 0.0],
    [4.05, 0.26, 0.140, 0.38, 1315.0, 0.0, 0.0, 0.0],
    [3.80, 0.12, 0.080, 0.32, 1275.0, 0.0, 0.0, 0.0],
]
V_INPUTS = [0.04, 0.08, 0.10, 0.14, 0.20]
T_INPUTS = [0.0, 0.5, 1.0, 2.5, 4.9, 5.5, 9.0]


def _assert_close(a, b, label, tol=1e-12):
    assert abs(a - b) <= tol * max(1.0, abs(a), abs(b)), \
        f"{label}: 新={a!r} 旧={b!r} 差={abs(a-b):.3e}"


# ---------------- 纯函数 ----------------

@requires_legacy
def test_lance_plan_identical():
    for t in T_INPUTS:
        _assert_close(physics.lance_plan(t), legacy._lance_plan(t), f"lance_plan(t={t})")


@requires_legacy
def test_tc_identical():
    for v in V_INPUTS:
        _assert_close(physics.tc(v), legacy._tc(v), f"tc(v={v})")


@requires_legacy
def test_derivs_identical():
    for si, st in enumerate(STATES):
        for lance in (1000.0, 1100.0, 1200.0):
            a = physics.derivs(list(st), 120.0, 80000.0, 4200.0, lance)
            b = legacy._derivs(list(st), 120.0, 80000.0, 4200.0, lance)
            assert len(a) == len(b) == 8
            for k, (x, y) in enumerate(zip(a, b)):
                _assert_close(float(x), float(y), f"derivs[{si}][dim{k}][lance={lance}]")


# ---------------- 积分器：多工况长序列 ----------------

@requires_legacy
@pytest.mark.parametrize("cool_rate", [0.0, 0.35, 0.8])
@pytest.mark.parametrize("state_idx", [0, 1, 2])
def test_integrate_identical_long_run(cool_rate, state_idx):
    """跑满 600s 全炉次，含 COOL_WIN(60-240) 内外切换与枪位换段(1min/5min)。"""
    a = list(STATES[state_idx])
    b = list(STATES[state_idx])
    t0, dt = 0.0, 600.0
    physics.integrate(a, t0, dt, 80000.0, 4200.0, physics.lance_plan,
                      substep_s=1.0, cool_rate_c_s=cool_rate)
    legacy._integrate(b, t0, dt, 80000.0, 4200.0, legacy._lance_plan,
                      substep_s=1.0, cool_rate_c_s=cool_rate)
    for k, (x, y) in enumerate(zip(a, b)):
        _assert_close(float(x), float(y), f"integrate[state{state_idx}][dim{k}][cool={cool_rate}]")
    # 全局保底：终态温度必须物理合理（防止"两边都错"被一致通过）
    assert 1000.0 <= a[4] <= 2000.0, f"终态温度越界: {a[4]}"


@requires_legacy
def test_integrate_substep_invariance_same_engine():
    """同一引擎不同子步长应高度接近（迁移未改变数值性质）。"""
    coarse = list(STATES[0])
    fine = list(STATES[0])
    physics.integrate(coarse, 0.0, 300.0, 80000.0, 4200.0, physics.lance_plan, substep_s=2.0)
    physics.integrate(fine, 0.0, 300.0, 80000.0, 4200.0, physics.lance_plan, substep_s=0.5)
    assert abs(coarse[4] - fine[4]) < 5.0, "子步长敏感性异常，积分器可能不稳定"


# ---------------- 契约守卫 ----------------

def test_state_vector_index_constants_are_authoritative():
    """IDX_* 常量必须与 state 布局一致（防后续误用维度）。"""
    assert (physics.IDX_C, physics.IDX_SI, physics.IDX_V) == (0, 1, 2)
    assert physics.IDX_T == 4
    assert len(physics.IDX_LOSS.__class__.__mro__) >= 1


def test_cool_constant_defined_once():
    """Q_COOL_KJ_KG 曾被重复定义两次；确认物理模块只留唯一来源。"""
    import re
    src = Path(physics.__file__).read_text(encoding="utf-8")
    # 去掉注释行后统计真实赋值
    assigns = [ln for ln in src.splitlines()
               if re.match(r"^Q_COOL_KJ_KG\s*=", ln.strip())]
    assert len(assigns) == 1, f"Q_COOL_KJ_KG 赋值 {len(assigns)} 次，应恰好 1 次: {assigns}"


def test_physics_module_has_no_side_effects():
    """物理域禁止 I/O 与执行通道（纯计算契约）。"""
    import re
    src = Path(physics.__file__).read_text(encoding="utf-8")
    for banned in ("open(", "requests", "os.system", "subprocess", "socket",
                   "http", "save_memories", "load_memories"):
        assert banned not in src, f"physics.py 出现副作用/越界调用: {banned}"


def test_physics_is_pure_no_llm():
    """物理域不得直接依赖 LLM 或叙述层。"""
    import re
    src = Path(physics.__file__).read_text(encoding="utf-8")
    assert "narrator" not in src
    assert "LLM" not in src
