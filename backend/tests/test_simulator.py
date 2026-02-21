import pytest
from app.tools.kinetics_simulator import simulate_blow_path
from app.schemas import SimulationInputs, IronInitialAnalysis

def test_simulator_basic_process():
    # Use higher Si to ensure exothermic reaction overcomes heat loss
    analysis = IronInitialAnalysis(C=4.2, Si=0.50, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = SimulationInputs(
        initial_temp_c=1300.0,
        initial_analysis=analysis,
        recipe={"ore": 0.0}, # No coolant
        duration_s=300
    )
    res = simulate_blow_path(inp)
    
    # Check if elements decrease
    final_si = res.final_analysis["Si"]
    final_v = res.final_analysis["V"]
    assert final_si < analysis.Si
    assert final_v < analysis.V
    
    # Check if temperature increases (oxidation is exothermic)
    assert res.final_temp_c > inp.initial_temp_c

def test_simulator_cooling_effect():
    analysis = IronInitialAnalysis(C=4.2, Si=0.50, V=0.28, Ti=0.1, P=0.08, S=0.03)
    
    # Case 1: No coolant
    inp1 = SimulationInputs(
        initial_temp_c=1350.0,
        initial_analysis=analysis,
        recipe={"ore": 0.0},
        duration_s=300
    )
    res1 = simulate_blow_path(inp1)
    
    # Case 2: Heavy coolant
    inp2 = SimulationInputs(
        initial_temp_c=1350.0,
        initial_analysis=analysis,
        recipe={"ore": 10.0}, # 10 tons of coolant
        duration_s=300
    )
    res2 = simulate_blow_path(inp2)
    
    # Coolant should result in lower final temperature
    assert res2.final_temp_c < res1.final_temp_c

def test_simulator_tc_crossover():
    # Start below Tc
    analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = SimulationInputs(
        initial_temp_c=1300.0,
        initial_analysis=analysis,
        recipe={"ore": 0.0},
        duration_s=600 # Long enough to cross Tc
    )
    res = simulate_blow_path(inp)
    
    # Should detect crossover
    if res.final_temp_c > 1361.0:
        assert res.tc_crossover_s is not None
        assert res.tc_crossover_s > 0

def test_simulator_soft_sensing():
    # Test sensor failure (Si/Ti near 0)
    analysis = IronInitialAnalysis(C=4.2, Si=0.0, V=0.28, Ti=0.0, P=0.08, S=0.03)
    inp = SimulationInputs(
        initial_temp_c=1350.0,
        initial_analysis=analysis,
        recipe={"ore": 0.0},
        duration_s=300
    )
    res = simulate_blow_path(inp)
    
    # Logic should detect low Si/Ti and use soft sensing values (Si=0.22, Ti=0.12)
    # The result mode should be 'soft-sensing'
    assert res.mode == "soft-sensing"
    
    # Verify that simulation proceeded (points generated)
    assert len(res.points) > 0
    # And final analysis should reflect oxidation from the soft-sensed values
    assert res.final_analysis["Si"] < 0.22
