import pytest
from app.tools.initial_charge import calculate_initial_charge
from app.schemas import InitialChargeInputs, IronInitialAnalysis


def _make(C=4.2, Si=0.20, V=0.28, Ti=0.10, P=0.08, S=0.03, weight=80.0, temp=1320.0, one_can=True):
    return InitialChargeInputs(
        iron_weight_t=weight,
        iron_temp_c=temp,
        iron_analysis=IronInitialAnalysis(C=C, Si=Si, V=V, Ti=Ti, P=P, S=S),
        is_one_can=one_can,
    )


def test_high_si_uses_v_slag_iron_not_pig_iron():
    """高 Si(≥0.20%) 启用钒渣铁, 不再使用已废弃的「生铁块」键"""
    res = calculate_initial_charge(_make(Si=0.30, temp=1350.0))
    assert "钒渣铁" in res.recipe
    assert "生铁块" not in res.recipe
    assert any("高硅铁水" in w for w in res.warnings)


def test_low_si_skips_v_slag_iron():
    """低 Si(<0.20%) 不加钒渣铁, 只用氧化铁皮 + 球返/球团"""
    res = calculate_initial_charge(_make(Si=0.12, temp=1300.0))
    assert "钒渣铁" not in res.recipe
    assert "氧化铁皮" in res.recipe
    assert "球返/球团" in res.recipe


def test_coolant_priority_and_cap():
    """分配优先级: 钒渣铁(≤2t) > 氧化铁皮(≤0.5t) > 球返/球团(余量)"""
    res = calculate_initial_charge(_make(Si=0.30, temp=1350.0))
    assert res.recipe["钒渣铁"] == 2.0   # 达上限
    assert res.recipe["氧化铁皮"] == 0.5  # 达上限
    assert res.recipe["球返/球团"] > 0


def test_oxygen_balance_value():
    """氧平衡锁定当前专家B口径: Σ(Si/C/V/Ti 氧化)×系数 ÷0.9 效率"""
    res = calculate_initial_charge(_make(Si=0.20, V=0.28))
    assert res.oxygen_total_m3 == 836.9


def test_v_si_ti_ratio_warning():
    """V/(Si+Ti) < 1.0 触发渣品位预警"""
    res = calculate_initial_charge(_make(Si=0.30, V=0.28, Ti=0.30))
    assert res.v_si_ti_ratio < 1.0
    assert any("渣品位" in w for w in res.warnings)


def test_outputs_positive():
    res = calculate_initial_charge(_make())
    assert res.oxygen_total_m3 > 0
    assert res.slag_weight_t > 0
    assert res.v_si_ti_ratio > 0
