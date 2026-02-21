from __future__ import annotations

from app.schemas import IronInitialAnalysis, ProcessData, SlagAnalysis
from app.tools.critical_temp import predict_critical_temp
from app.tools.diagnose_process_quality import diagnose_process_quality
from app.tools.lance_profile import recommend_lance_profile
from app.tools.thermal_balance import ThermalBalanceInputs, calculate_thermal_balance


def test_calculate_thermal_balance_low_si() -> None:
    out = calculate_thermal_balance(ThermalBalanceInputs(iron_temp_c=1280, si_content_pct=0.20, is_one_can=False))
    assert out.coolant_type.value == "弃渣球"
    assert out.add_within_minutes == 2.5
    # Updated for Danieli Model (approx 81 kg/t additional coolant needed with default 10t scrap)
    assert 70.0 <= out.kg_per_t <= 90.0


def test_calculate_thermal_balance_high_si_one_can() -> None:
    out = calculate_thermal_balance(ThermalBalanceInputs(iron_temp_c=1340, si_content_pct=0.28, is_one_can=True))
    assert out.coolant_type.value == "球返"
    # Updated for Danieli Model (higher temp + higher Si = more heat = more coolant)
    assert 110.0 <= out.kg_per_t <= 140.0
    assert any("一罐到底" in n for n in out.notes)


def test_recommend_lance_profile_high_si() -> None:
    out = recommend_lance_profile(si_content_pct=0.28)
    assert out.mode.value == "恒定低枪位模式"
    assert len(out.steps) == 1
    assert 900 <= out.steps[0].lance_height_mm <= 1000
    assert "900mm" in out.endgame_action


def test_recommend_lance_profile_low_si() -> None:
    out = recommend_lance_profile(si_content_pct=0.18)
    assert out.mode.value == "低-高-低模式"
    assert len(out.steps) == 3
    assert out.steps[0].lance_height_mm < out.steps[1].lance_height_mm


def test_predict_critical_temp_default_base() -> None:
    out = predict_critical_temp()
    assert out.t_critical_c == 1361.0


def test_predict_critical_temp_with_v_and_margin() -> None:
    out = predict_critical_temp(v_content_pct=0.20, current_temp_c=1368.0)
    assert out.t_critical_c == 1367.4
    assert out.margin_c == 0.6


def test_diagnose_process_quality_ratio_and_tap_time() -> None:
    slag = SlagAnalysis(V2O5=1.0, SiO2=1.0, TiO2=1.0, CaO=45.0)
    process = ProcessData(tap_time_min=3.0, coolant_type_used="弃渣球", coolant_structure_notes=["批次A"])
    iron = IronInitialAnalysis(C=4.2, Si=0.3, V=0.28, Ti=0.1, P=0.08, S=0.03)
    out = diagnose_process_quality(slag=slag, process=process, iron_analysis=iron)
    titles = [f.title for f in out.findings]
    assert any("出钢时间过短" in t for t in titles)


def test_diagnose_process_quality_no_findings() -> None:
    slag = SlagAnalysis(V2O5=None, SiO2=None, TiO2=None)
    process = ProcessData(tap_time_min=None)
    iron = IronInitialAnalysis(C=4.2, Si=0.20, V=0.30, Ti=0.05, P=0.08, S=0.03)
    out = diagnose_process_quality(slag=slag, process=process, iron_analysis=iron)
    # With V=0.30 and Si=0.20, ratio = 0.30 / 0.25 = 1.2 > 1.01, so no "Raw Material Deficit"
    # tap_time_min is None, so no "Tap Time Short"
    # slag.V2O5 is None, so no "Low V2O5"
    # slag.CaO is None, so no "Slag Contamination"
    # iron.Si=0.20 < 0.25, so no "High Si Dilution"
    # Should have "提钒过程质量受控"
    assert len(out.findings) == 1
    assert out.findings[0].severity == "low"
    assert "受控" in out.findings[0].title

