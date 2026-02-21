import sys
import os
sys.path.append(os.getcwd() + "/backend")

from app.tools.kinetics_simulator import simulate_blow_path
from app.schemas import SimulationInputs, IronInitialAnalysis

def test_kinetics():
    print("--- Testing Kinetics Simulator ---")
    inputs = SimulationInputs(
        initial_temp_c=1250.0,
        initial_analysis=IronInitialAnalysis(
            C=4.2, Si=0.30, V=0.35, Ti=0.15, P=0.1, S=0.03
        ),
        recipe={
            "iron_weight": 100.0,
            "scrap_weight": 10.0,
            "lime_weight": 3.0,
            "ore_weight": 1.0
        },
        oxygen_flow_rate_m3h=24000.0,
        duration_s=600 # 10 min
    )
    result = simulate_blow_path(inputs)
    
    print(f"Final Temp: {result.final_temp_c} C")
    print(f"Tc Crossover: {result.tc_crossover_s} s")
    print(f"Advice: {result.proactive_advice}")
    
    print("\nTime | Temp | C%   | Si%  | V%   | Ti%")
    print("-" * 40)
    for p in result.points[::6]: # Print every 60s
        print(f"{p.time_s:4d} | {p.temp_c:4.0f} | {p.C_pct:4.2f} | {p.Si_pct:4.2f} | {p.V_pct:4.2f} | {p.Ti_pct:4.2f}")

if __name__ == "__main__":
    test_kinetics()
