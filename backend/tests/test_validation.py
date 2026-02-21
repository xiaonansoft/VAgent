import pytest
from pydantic import ValidationError
from app.schemas import IronInitialAnalysis, InitialChargeInputs, SimulationInputs

def test_iron_analysis_validation():
    # Valid case
    valid = IronInitialAnalysis(C=4.2, Si=0.2, V=0.3, Ti=0.1, P=0.05, S=0.02)
    assert valid.C == 4.2

    # Invalid case: Negative value
    with pytest.raises(ValidationError):
        IronInitialAnalysis(C=-1.0, Si=0.2, V=0.3, Ti=0.1, P=0.05, S=0.02)

    # Invalid case: Extreme value (> 10%)
    with pytest.raises(ValidationError):
        IronInitialAnalysis(C=12.0, Si=0.2, V=0.3, Ti=0.1, P=0.05, S=0.02)

def test_initial_charge_inputs_validation():
    analysis = IronInitialAnalysis(C=4.0, Si=0.2, V=0.3, Ti=0.1, P=0.05, S=0.02)
    
    # Valid case
    valid = InitialChargeInputs(
        iron_weight_t=100.0,
        iron_temp_c=1350.0,
        iron_analysis=analysis,
        is_one_can=True,
        target_temp_c=1380.0
    )
    assert valid.iron_weight_t == 100.0

    # Invalid case: Weight too low (< 50)
    with pytest.raises(ValidationError):
        InitialChargeInputs(
            iron_weight_t=10.0,
            iron_temp_c=1350.0,
            iron_analysis=analysis,
            is_one_can=True
        )

    # Invalid case: Temp too high (> 1600)
    with pytest.raises(ValidationError):
        InitialChargeInputs(
            iron_weight_t=100.0,
            iron_temp_c=1700.0,
            iron_analysis=analysis,
            is_one_can=True
        )

def test_simulation_inputs_validation():
    analysis = IronInitialAnalysis(C=4.0, Si=0.2, V=0.3, Ti=0.1, P=0.05, S=0.02)
    
    # Valid case
    valid = SimulationInputs(
        initial_temp_c=1350.0,
        initial_analysis=analysis,
        recipe={"ore": 1.0},
        oxygen_flow_rate_m3h=20000.0,
        duration_s=600
    )
    assert valid.initial_temp_c == 1350.0

    # Invalid case: Duration too short (< 60)
    with pytest.raises(ValidationError):
        SimulationInputs(
            initial_temp_c=1350.0,
            initial_analysis=analysis,
            recipe={"ore": 1.0},
            duration_s=30
        )
