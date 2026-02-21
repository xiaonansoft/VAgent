from app.tools.initial_charge import calculate_initial_charge
from app.tools.kinetics_simulator import simulate_blow_path
from app.schemas import InitialChargeInputs, IronInitialAnalysis, SimulationInputs

def test_initial_charge_v6():
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.28, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1340,
        iron_analysis=iron_analysis,
        is_one_can=True
    )
    res = calculate_initial_charge(inp)
    assert res.oxygen_total_m3 > 0
    assert "生铁块" in res.recipe or "氧化铁皮" in res.recipe
    assert res.slag_weight_t > 0

def test_kinetics_simulator_v6():
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.28, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = SimulationInputs(
        initial_temp_c=1340,
        initial_analysis=iron_analysis,
        recipe={"生铁块": 2.5}
    )
    res = simulate_blow_path(inp)
    assert len(res.points) > 0
    assert res.final_analysis["V"] < 0.28
    assert res.final_temp_c > 1300
