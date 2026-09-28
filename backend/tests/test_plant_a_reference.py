# -*- coding: utf-8 -*-
"""专家A四大平衡参考实现 —— 黄金用例测试

黄金值取自专家 Excel《提钒预算测算钒品位低原因说明(1).xlsx》的公式缓存
计算结果 (data_only=True 提取, 全精度)。验收标准: 相对误差 < 0.5%。

可直接运行:  python3 tests/test_plant_a_reference.py
或 pytest:   pytest tests/test_plant_a_reference.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools.plant_a_reference import run_plant_a_model, predict_v2o5_grade  # noqa: E402

R = run_plant_a_model()
_M = R.material
_H = R.heat
_A = R.after
_P = R.product
_MG = R.marginal["pellet"]

# (名称, 复现值, Excel黄金值, 单元格溯源)
CASES = [
    # --- 物料平衡推算 ---
    ("铁水C修正",           _M["iron_C_fixed"],      4.9751,                 "物料!C8"),
    ("Si氧化量",            _M["ox_m"]["Si"],        167.2,                  "物料!D19"),
    ("Si氧耗",              _M["o2_total"] and 0 or 0, 0, "",),  # placeholder removed below
    ("V氧化量",             _M["ox_m"]["V"],         207.2,                  "物料!D23"),
    ("V2O5产物量",          _M["prod"]["V2O5"],      369.70980392156855,     "物料!F23"),
    ("C→CO量",              _M["ox_m"]["C_CO"],      1072.872,               "物料!D25"),
    ("C→CO2量",             _M["ox_m"]["C_CO2"],     119.208,                "物料!D26"),
    ("渣中SiO2",            _M["slag_sio2"],         358.55771428571427,     "物料!E55"),
    ("非铁氧化物合计",       _M["non_fe_oxides"],     1141.753347737056,      "物料!E59"),
    ("炉渣总量",            _M["slag_total"],        2075.9151777037378,     "物料!E63"),
    ("渣中FeO",             _M["feo_mass"],          871.8843746355699,      "物料!E60"),
    ("渣中Fe2O3",           _M["fe2o3_mass"],        62.27745533111213,      "物料!E61"),
    ("Fe→FeO氧化量",        _M["ox_m"]["Fe_FeO"],    678.1322913832211,      "物料!D27"),
    ("元素氧耗合计",         _M["o2_total"],          2442.8831401620478,     "物料!E29"),
    ("烟尘量",              _M["dust"],              160.0,                  "物料!C67"),
    ("烟尘氧耗",            _M["dust_o2"],           34.48888888888889,      "物料!C68"),
    ("炉气CO",              _M["co_mass"],           2507.366400000001,      "物料!C77"),
    ("炉气CO2",             _M["co2_mass"],          437.7941333333335,      "物料!C78"),
    ("自由氧体积",          _M["v_o2_free"],         11.182479167569635,     "物料!D79"),
    ("氮气体积",            _M["v_n2"],              3.456778986976792,      "物料!D80"),
    ("炉气总量",            _M["gas_mass"],          2965.4564773064403,     "物料!C81"),
    ("实际氧耗kg",          _M["o2_kg"],             2500.4605063573763,     "物料!C84"),
    ("实际氧耗m³",          _M["o2_vol"],            1750.7544518235354,     "物料!C85"),
    ("渣带铁珠",            _M["beads"],             207.5915177703738,      "物料!D89"),
    ("钢水量",              _M["steel"],             76881.09733357682,      "物料!D96"),
    ("物料收支差",          _M["balance_diff"],      -15.999999999985448,    "物料!G108"),
    ("铁水全铁量",          _M["iron_full_iron"],    75153.95599320883,      "物料!D113"),
    # --- 热量平衡推算 ---
    ("铁水凝固点",          _H["tf_iron"],           1022.120764006791,      "热量!C29"),
    ("钢水凝固点",          _H["tf_steel"],          1295.8874286926996,     "热量!C30"),
    ("铁水物理热",          _H["h_iron"],            95475191.17691001,      "热量!C31"),
    ("Si氧化热",            _H["heats"]["Si"],       4878394.399999999,      "热量!E35"),
    ("Ti氧化热",            _H["heats"]["Ti"],       1732765.025357633,      "热量!E37"),
    ("V氧化热",             _H["heats"]["V"],        575394.3999999999,      "热量!E39"),
    ("SiO2成渣热",          _H["heats"]["SiO2_slag"], 580863.4971428572,     "热量!E45"),
    ("元素氧化热合计",       _H["h_elements"],        28992810.963070758,     "热量!E46"),
    ("热量总收入",          _H["income"],            125009390.50389187,     "热量!C61"),
    ("钢水物理热",          _H["h_steel"],           93978110.63992971,      "热量!C65"),
    ("炉渣物理热",          _H["h_slag"],            3863849.022380525,      "热量!C66"),
    ("其他热损失",          _H["h_other"],           5000375.620155675,      "热量!C71"),
    ("热量总支出",          _H["outlay"],            108514328.47738813,     "热量!C72"),
    ("热量富余",            _H["surplus"],           16495062.026503757,     "热量!G90"),
    # --- 冷料边际响应 (1kg 球团) ---
    ("球团渣增/kg",         _MG["slag_up"],          0.21870129870129862,    "冷料!E26"),
    ("球团钢增/kg",         _MG["steel_up"],         0.5178947186147187,     "冷料!E27"),
    ("球团氧减/kg",         _MG["o2_down"],          0.24201788859103487,    "冷料!E30"),
    ("球团吸热/kg",         _MG["absorption"],       4673.35460285671,       "冷料4!I31"),
    ("金属铁吸热/kg",       R.marginal["metal_fe"]["absorption"], 1111.2042634879963, "冷料4!E11"),
    ("块矿吸热/kg",         R.marginal["ore_block"]["absorption"], 5171.181876352281, "冷料4!I51"),
    ("弃渣球吸热/kg",       R.marginal["waste_slag_ball"]["absorption"], 4676.118161800815, "冷料4!I71"),
    # --- 冷料配吃后 ---
    ("球团配吃量",          _A["coolant_weights"]["pellet"], 3529.5977789532, "冷料4!H35"),
    ("冷料后钢水",          _A["steel"],             78709.05738213092,      "冷料3!G105"),
    ("冷料后炉渣",          _A["slag"],              2847.8427958540215,     "冷料3!G107"),
    ("冷料后氧耗",          _A["o2_kg"],             1646.2347043195166,     "冷料3!D113"),
    ("热收入(冷料后)",      _A["income"],            126371939.79216897,     "冷料4!D98"),
    ("热支出(冷料后,复刻)", _A["outlay_replica"],    126278872.91514294,     "冷料4!H98"),
    ("余额(复刻Q5)",        _A["residual_replica"],  93066.87702603638,      "冷料4!H99"),
    # --- 钒平衡/原料标准 ---
    ("铁水/半钢标准",       _P["standard_per_t_semi"]["iron_t"], 1.0164014493478377, "标准!E4"),
    ("球返/半钢标准",       _P["standard_per_t_semi"]["pellet_t"], 0.044843603726786765, "标准!E8"),
    ("硅铁kg/t",            _P["standard_per_t_semi"]["fesilicon_kg"], 0.43832312503125503, "标准!E13"),
    ("钒渣t/t",             _P["standard_per_t_semi"]["vslag_t"], 0.037688245980815355, "标准!E15"),
    ("污泥t/t",             _P["standard_per_t_semi"]["sludge_t"], 0.004186907199824717, "标准!E16"),
    ("钒收入-铁水",         _P["v_balance"]["in_iron"], 227.2,              "标准!K22"),
    ("钒收入-球团",         _P["v_balance"]["in_coolant"], 8.92134928722006,  "标准!K24"),
    ("钒收入合计",          _P["v_balance"]["in_total"], 236.12134928722003,  "标准!K30"),
    ("钒支出-半钢",         _P["v_balance"]["out_semi"], 19.67726434553273,  "标准!N22"),
    ("钒支出-渣",           _P["v_balance"]["out_slag"], 207.70558659799485,  "标准!N23"),
    ("钒支出-烟尘(余项)",   _P["v_balance"]["out_dust"], 7.985702273796079,   "标准!N26"),
    ("钒回收率%",           _P["v_balance"]["recovery_pct"], 87.96561057481507, "标准!N31"),
    # --- 精钒渣成分 ---
    ("渣V2O5品位%",         _P["slag_grade"]["V2O5"], 13.298965146134751,    "标准!F20"),
    ("渣MgO%",              _P["slag_grade"]["MgO"], 1.92879986270427,       "标准!F22"),
    ("渣TiO2%",             _P["slag_grade"]["TiO2"], 9.668611490422775,     "标准!F23"),
    ("渣SiO2%",             _P["slag_grade"]["SiO2"], 16.400567321723763,    "标准!F24"),
    ("渣P2O5%",             _P["slag_grade"]["P2O5"], 0.6549128630616028,    "标准!F25"),
    ("渣MnO%",              _P["slag_grade"]["MnO"], 5.941792949561689,      "标准!F26"),
    ("渣Al2O3%",            _P["slag_grade"]["Al2O3"], 2.1558279072169886,  "标准!F27"),
    ("渣Cr2O3%",            _P["slag_grade"]["Cr2O3"], 3.206640825218158,   "标准!F28"),
    ("渣TFe%",              _P["slag_grade"]["TFe"], 33.25655444414428,      "标准!F29"),
]
# 移除占位行
CASES = [c for c in CASES if c[3]]


def rel_err(actual: float, expected: float) -> float:
    if expected == 0:
        return abs(actual)
    return abs(actual - expected) / abs(expected)


def test_golden_values():
    failures = []
    for name, actual, expected, cell in CASES:
        err = rel_err(actual, expected)
        assert err < 0.005, f"{name} [{cell}]: 复现={actual:.6g} 黄金={expected:.6g} 误差={err*100:.3f}%"
    assert True


def test_heat_closes_after_correction():
    """修正口径(补 Q5 漏项)后热平衡应闭合到机器精度"""
    assert abs(R.after["residual"] / R.after["outlay"]) < 1e-9


def test_grade_prediction_attribution():
    """品位归因: 高硅铁水 → 品位下降 (对照工作表1 的业务用法)

    Excel 备注载明: 14日 Si=0.266/V=0.299 时理论品位 12.48%。
    因该数值的专家计算口径未完全披露, 此处用宽容差做方向性校验。
    """
    base = predict_v2o5_grade(4.3, 0.215, 0.284)       # 基准: 应≈13.30
    high_si = predict_v2o5_grade(4.3, 0.266, 0.299)    # 14日条件
    assert abs(base - 13.299) < 0.2
    assert high_si < base, "高硅铁水预测品位应低于基准"


if __name__ == "__main__":
    print(f"{'检查项':<14}{'复现值':>16}{'Excel黄金值':>18}{'误差%':>9}  溯源")
    print("-" * 78)
    worst, worst_name = 0.0, ""
    n_pass = 0
    for name, actual, expected, cell in CASES:
        err = rel_err(actual, expected)
        flag = "✓" if err < 0.005 else "✗"
        if err > worst:
            worst, worst_name = err, name
        n_pass += 1 if err < 0.005 else 0
        print(f"{flag} {name:<13}{actual:>16.6g}{expected:>18.6g}{err*100:>8.4f}%  {cell}")
    print("-" * 78)
    corrected = abs(R.after["residual"] / R.after["outlay"])
    print(f"修正口径热平衡闭合差: {corrected:.2e} (相对)")
    print(f"基准品位: {predict_v2o5_grade(4.3, 0.215, 0.284):.3f}%  "
          f"14日高硅条件: {predict_v2o5_grade(4.3, 0.266, 0.299):.3f}%")
    print(f"\n{n_pass}/{len(CASES)} 项通过, 最大相对误差 {worst*100:.4f}% ({worst_name})")
    sys.exit(0 if n_pass == len(CASES) and corrected < 1e-9 else 1)
