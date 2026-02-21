import sys
import os
sys.path.append(os.getcwd() + "/backend")

from app.tools.initial_charge import calculate_initial_charge
from app.tools.lance_profile import recommend_lance_profile
from app.schemas import InitialChargeInputs, IronInitialAnalysis

def test_jianlong_process():
    print("--- Testing Jianlong Process Logic ---")
    
    # Case 1: Low Si (<0.15)
    print("\nCase 1: Low Si (0.12%), Temp 1280")
    inputs_low = InitialChargeInputs(
        iron_weight_t=100.0,
        iron_temp_c=1280.0,
        iron_analysis=IronInitialAnalysis(C=4.0, Si=0.12, V=0.3, Ti=0.1, P=0.1, S=0.03),
        is_one_can=False
    )
    res_low = calculate_initial_charge(inputs_low)
    print(f"Recipe: {res_low.recipe}")
    print(f"Warnings: {res_low.warnings}")
    
    prof_low = recommend_lance_profile(si_content_pct=0.12)
    print("Lance Steps:", [(s.lance_height_mm) for s in prof_low.steps])
    
    # Case 2: High Si (>0.25), High Temp (1350)
    print("\nCase 2: High Si (0.28%), Temp 1350")
    inputs_high = InitialChargeInputs(
        iron_weight_t=100.0,
        iron_temp_c=1350.0,
        iron_analysis=IronInitialAnalysis(C=4.0, Si=0.28, V=0.3, Ti=0.1, P=0.1, S=0.03),
        is_one_can=False
    )
    res_high = calculate_initial_charge(inputs_high)
    print(f"Recipe: {res_high.recipe}") # Expect V-Slag-Iron and more coolant
    
    prof_high = recommend_lance_profile(si_content_pct=0.28)
    print("Lance Steps:", [(s.lance_height_mm) for s in prof_high.steps])

if __name__ == "__main__":
    test_jianlong_process()
