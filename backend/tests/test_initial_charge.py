import pytest
from app.tools.initial_charge import calculate_initial_charge
from app.schemas import InitialChargeInputs, IronInitialAnalysis

def test_initial_charge_high_si():
    # High Si content (0.5%) should trigger specific logic
    analysis = IronInitialAnalysis(C=4.2, Si=0.5, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1350.0,
        iron_analysis=analysis,
        is_one_can=True
    )
    res = calculate_initial_charge(inp)
    
    # Check if result is valid
    assert res.oxygen_total_m3 > 0
    # High Si implies more heat, so maybe more coolant needed
    assert res.recipe.get("生铁块", 0) > 0 or res.recipe.get("氧化铁皮", 0) > 0

def test_initial_charge_low_temp():
    # Low temperature (1250C) might need less coolant
    analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1250.0,
        iron_analysis=analysis,
        is_one_can=True
    )
    res = calculate_initial_charge(inp)
    
    # Check warnings
    assert any("温度" in w for w in res.warnings) or res.recipe.get("生铁块", 0) == 0

def test_initial_charge_extreme_weight():
    # Very small batch (50t)
    analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=50.0,
        iron_temp_c=1350.0,
        iron_analysis=analysis,
        is_one_can=True
    )
    res = calculate_initial_charge(inp)
    assert res.slag_weight_t > 0
