from app.tools.initial_charge import calculate_initial_charge
from app.schemas import InitialChargeInputs, IronInitialAnalysis

def test_sdm_standard_case():
    """测试标准工况下的配料计算"""
    # V=0.45, Si=0.2, Ti=0.1 -> Ratio = 0.45 / 0.3 = 1.5 > 1.05
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.45, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1320,
        iron_analysis=iron_analysis,
        is_one_can=False,
        target_temp_c=1360.0
    )
    res = calculate_initial_charge(inp)
    
    # 验证输出结构
    assert "生铁块" in res.recipe
    assert res.oxygen_total_m3 > 0
    assert res.slag_weight_t > 0
    assert res.v_si_ti_ratio == 1.5

def test_sdm_one_can_bonus():
    """测试一罐到底工艺的热补偿与渣量增量"""
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.45, Ti=0.1, P=0.08, S=0.03)
    
    # 非一罐到底
    inp_normal = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1320,
        iron_analysis=iron_analysis,
        is_one_can=False
    )
    res_normal = calculate_initial_charge(inp_normal)
    
    # 一罐到底
    inp_one_can = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1320,
        iron_analysis=iron_analysis,
        is_one_can=True
    )
    res_one_can = calculate_initial_charge(inp_one_can)
    
    # 验证：一罐到底因为有效温度更高，冷却剂（生铁块）应该更多
    assert res_one_can.recipe["生铁块"] > res_normal.recipe["生铁块"]
    # 验证：一罐到底渣量增加 10% (允许浮动，因为模型内部是先计算再四舍五入)
    import pytest
    assert res_one_can.slag_weight_t == pytest.approx(res_normal.slag_weight_t * 1.1, abs=0.02)
    assert any("一罐到底" in w for w in res_one_can.warnings)

def test_sdm_low_v_ratio():
    """测试 V/(Si+Ti) 比例偏低时的冷却剂切换逻辑"""
    # Si=0.2, Ti=0.1 -> Sum=0.3. V=0.28 -> Ratio = 0.933 < 1.05
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1320,
        iron_analysis=iron_analysis,
        is_one_can=True
    )
    res = calculate_initial_charge(inp)
    
    # 验证：比例偏低应推荐“氧化铁皮”
    assert "氧化铁皮" in res.recipe
    assert "生铁块" not in res.recipe
    assert any("极难富集" in w for w in res.warnings)

def test_sdm_high_si_warning():
    """测试高硅铁水下的预警与冷却剂逻辑"""
    # Si=0.35, Ti=0.1 -> Sum=0.45. V=0.5 -> Ratio = 0.5 / 0.45 = 1.11 > 1.05
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.35, V=0.50, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1320,
        iron_analysis=iron_analysis,
        is_one_can=False
    )
    res = calculate_initial_charge(inp)
    
    # 验证：高硅应触发“生铁块”推荐与预警
    assert "生铁块" in res.recipe
    assert any("高硅铁水" in w for w in res.warnings)

def test_sdm_oxygen_balance():
    """测试氧平衡计算的准确性"""
    # 铁水 80t, Si 0.2%, V 0.28%, C 4.2%
    # delta_Si = 0.2% * 80t = 160kg
    # delta_V = (0.28% - 0.03%) * 80t = 0.25% * 80t = 200kg
    # delta_C = (4.2% - 3.5%) * 80t = 0.7% * 80t = 560kg
    # Oxy = 160*0.8 + 200*0.5 + 560*0.93 = 128 + 100 + 520.8 = 748.8
    iron_analysis = IronInitialAnalysis(C=4.2, Si=0.20, V=0.28, Ti=0.1, P=0.08, S=0.03)
    inp = InitialChargeInputs(
        iron_weight_t=80.0,
        iron_temp_c=1320,
        iron_analysis=iron_analysis,
        is_one_can=False
    )
    res = calculate_initial_charge(inp)
    
    assert res.oxygen_total_m3 == 748.8
