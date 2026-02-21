from app.tools.equilibrium_model import calculate_equilibrium_state
from app.schemas import SimulationInputs, IronInitialAnalysis

def test_equilibrium_model_basic():
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.28, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = SimulationInputs(
        initial_temp_c=1340,
        initial_analysis=iron_analysis,
        recipe={"生铁块": 2.5},
        oxygen_flow_rate_m3h=22000.0,
        duration_s=360
    )
    
    res = calculate_equilibrium_state(inp)
    
    # Assertions
    # Final temperature should be higher than initial due to oxidation (even with coolant)
    assert res["final_temp_c"] > 1340
    
    # Si and Ti should be almost completely oxidized in equilibrium
    assert res["final_analysis"]["Si"] < 0.05
    assert res["final_analysis"]["Ti"] < 0.05
    
    # V should be oxidized significantly but maybe not fully if O2 is limited (though 360s is long)
    # Actually with 22000 m3/h for 6min, we have plenty of oxygen for Si/Ti/V.
    assert res["final_analysis"]["V"] < 0.1
    
    # C should be partially oxidized
    assert res["final_analysis"]["C"] < 4.2
