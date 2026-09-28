# -*- coding: utf-8 -*-
"""专家A提钒四大平衡参考实现 (PlantA Four-Balance Reference Model)

从专家 Excel《提钒预算测算钒品位低原因说明(1).xlsx》(8 表 703 公式) 逐公式
翻译而来。计算链路:

    基表(成分/指标) → 物料平衡 → 热量平衡(热量富余)
    → 冷料配吃(边际响应反算冷料量) → 钒平衡/原料标准 → 钒渣品位预测

设计原则:
1. 所有专家常数集中在本模块顶部, 每条带 Excel 单元格溯源注释 ——
   后续迁 YAML 知识包时, 这些注释即 provenance 字段。
2. 忠实复刻 Excel 行为(包括已发现的引用怪癖), 怪癖处用 Q1-Q6 标注;
   同时提供 `corrected=True` 的修正口径, 供仲裁对照。
3. 纯标准库实现, 无第三方依赖, 便于在任何环境验证。

已发现的 Excel 引用怪癖 (详见 PLANT_A_EXCEL_DECODED.md §5):
- Q1: 物料平衡!D89 (渣带铁珠) 用 D88=0.1 直接相乘, 而冷料表金属铁 D9 用
      D88% (=0.001), 两者口径不一致; 仅影响金属铁冷料。
- Q2: 冷料"弃渣/铬渣球"的渣量增加未除以 (1-FeO%-Fe2O3%), 与球团口径不一致。
- Q3: 冷料"金属铁"的氧耗做了双重 /99.8% (D12 与 E11 各除一次)。
- Q4: "块矿"的 SiO2 成渣热引用了球团的 SiO2 含量 (物料平衡!D34)。
- Q5: 热平衡终算表漏加球团的"渣中金属铁珠物理热"(F37), 导致余额 H99
      恰好等于该项; corrected 口径补上后热平衡闭合至 ~1e-9。
- Q6: "金属铁"的 1kg 吸热公式引用了外部工作簿 [15], 本簿内不可完整复算,
      其吸热量 1111.2 kJ/kg 按给定常数处理。
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

# ============================================================================
# 专家常数 (源: 专家A Excel, 单元格溯源见注释)
# ============================================================================

# --- 成分修正 ---
IRON_C_LAB_FACTOR = 1.157          # 物料平衡!C8: 入炉C = 化验C × 1.157
HOT_METAL_SLAG_RATIO = 0.0005      # 冷料!D106: 铁水带渣 0.5‰ 铁水量

# --- 氧化产物分配 (物料平衡) ---
CO_SHARE = 0.90                    # !D25: 碳氧化生成 CO 比例
CO2_SHARE = 0.10                   # !D26: 碳氧化生成 CO2 比例
SLAG_FEO = 0.42                    # !F47: 渣中 FeO 比例
SLAG_FE2O3 = 0.03                  # !G47: 渣中 Fe2O3 比例
SLAG_IRON_BEADS = 0.10             # !D88: 渣带金属铁珠 = 渣量 × 10%
SPITTING_RATIO = 0.003             # !D92: 喷溅铁损 = 金属料 × 0.3%
DUST_RATIO = 0.002                 # !C66: 烟尘 = 金属料 × 0.2% (技术处 周胜刚)
DUST_FEO = 0.70                    # !C66: 烟尘中 FeO 比例
DUST_FE2O3 = 0.20                  # !C66: 烟尘中 Fe2O3 比例
LINING_RATIO = 0.00017             # !L38: 炉衬侵蚀 = 金属料 × 0.017%
LINING = {"CaO": 0.02, "SiO2": 0.02, "MgO": 0.81, "Al2O3": 0.01, "C": 0.14}  # !C38..K38
FREE_O2_PCT = 0.005                # !F79: 炉气自由氧体积比 0.5%
O2_PURITY = 0.998                  # !F79: 氧气纯度 99.8%

# --- 热力学 (热量平衡 表2.1/2.2) ---
CP = {
    "iron":  {"cp_s": 0.745, "L": 218.0, "cp_l": 0.837},   # !C5:E5 《转炉炼钢问答》
    "steel": {"cp_s": 0.699, "L": 272.0, "cp_l": 0.837},   # !C6:E6
    "slag":  {"cp_l": 1.247, "L": 209.0},                  # !D7:E7
    "gas":   {"cp_l": 1.141},                              # !E8
    "dust":  {"cp_l": 0.996, "L": 209.0},                  # !D9:E9
}
# 1kg 元素氧化反应热 ΔH [kJ/kg 元素]
DH_SI = 29177.0                    # !E15
DH_MN = 6593.0                     # !E16
DH_TI = DH_SI / 1.89 * 1.38        # !E17: 秘诀——Ti 冷却效应按 Si 的 1.38/1.89 折算
DH_V = 2777.0                      # !E18: ⚠️ 与文献值(~15000)差异大, 待专家仲裁
DH_P = 18980.0                     # !E19
DH_C_CO = 11637.0                  # !E20
DH_C_CO2 = 34824.0                 # !E21
DH_FE_FEO = 4249.0                 # !E22
DH_FE_FE2O3 = 6459.0               # !E23
DH_CR = 7598.0                     # !E24
DH_SIO2_SLAG = 1620.0              # !E25: SiO2+2CaO 成渣热

# --- 温度假设 ---
GAS_TEMP = 1450.0                  # !D67: 炉气温度
SPIT_TEMP = 1600.0                 # !D70: 喷溅金属温度
SLAG_TEMP_DELTA = 20.0             # !D66: 渣温 = 钢水终点温度 - 20
OTHER_HEAT_LOSS = 0.04             # !C71: 其他热损失 = 热收入 × 4%
AMBIENT_TEMP = 25.0                # !D65: 常温 25°C

# --- 化学计量 (分子量比) ---
MW = {
    "SiO2_per_Si": 60 / 28, "O2_per_Si": 32 / 28,
    "MnO_per_Mn": 71 / 55,  "O2_per_Mn": 16 / 55,
    "TiO2_per_Ti": 80 / 48, "O2_per_Ti": 32 / 48,
    "Cr2O3_per_Cr": 150 / 102, "O2_per_Cr": 48 / 102,
    "V2O5_per_V": 182 / 102, "O2_per_V": 80 / 102,
    "P2O5_per_P": 142 / 62, "O2_per_P": 80 / 62,
    "CO_per_C": 28 / 12, "O2_per_C_CO": 16 / 12,
    "CO2_per_C": 44 / 12, "O2_per_C_CO2": 32 / 12,
    "Fe_per_FeO": 56 / 72, "O2_per_Fe_FeO": 16 / 56,
    "Fe_per_Fe2O3": 112 / 160, "O2_per_Fe_Fe2O3": 48 / 112,
}
FE_IN_FEO = 56 / 72                # 0.7778: FeO 中 Fe 占比
FE_IN_FE2O3 = 112 / 160            # 0.7:    Fe2O3 中 Fe 占比
V2O5_PER_V = 182 / 102             # 1.7843: V→V2O5 质量比

# --- 产品换算 (提钒转炉原料标准表) ---
V_RECOVERY_SLAG_FACTOR = 0.935     # !E15: 钒渣量→标准折算
V_IN_SLAG_FACTOR = 0.965           # !N23: 渣中 V 折算
TFE_FACTOR = 0.97                  # !F29: TFe 折算
SLUDGE_FACTOR_A = 0.85             # !E16: 除尘灰→污泥
SLUDGE_FACTOR_B = 0.62             # !E16
SLUDGE_ADD = 0.0014                # !E16


# --- 冷料规格 (映射自 基表/物料平衡 行34-37; 怪癖见模块 docstring Q1-Q6) ---
@dataclass(frozen=True)
class CoolantSpec:
    key: str
    label: str
    fe2o3: float                    # Fe2O3 质量分数
    sio2: float                     # SiO2 质量分数 (Q4: 块矿借用球团值)
    v2o5: float                     # V2O5 质量分数
    cao: float = 0.0
    mgo: float = 0.0
    al2o3: float = 0.0
    tio2: float = 0.0
    mno: float = 0.0
    cr2o3: float = 0.0
    metallic_fe_convention: bool = False  # Q1/Q3: 金属铁特殊口径
    no_slag_dilution: bool = False        # Q2: 渣量不除以 (1-FeO%-Fe2O3%)
    absorption_fixed: Optional[float] = None  # Q6: 金属铁吸热按外部簿给定值


# 映射: 球团←基表球返行, 金属铁←弃渣球行, 块矿←铁皮球行(SiO2借球团), 弃渣球←外购球行
COOLANTS: Dict[str, CoolantSpec] = {
    "pellet": CoolantSpec(
        "pellet", "球团矿(球返)", fe2o3=87.97142857142858 / 100, sio2=3.26 / 100,
        v2o5=0.451 / 100, cao=1.21 / 100, mgo=1.266 / 100, al2o3=1.76 / 100,
        tio2=4.07 / 100, mno=0.18 / 100, cr2o3=0.2904 / 100),
    "metal_fe": CoolantSpec(
        "metal_fe", "金属铁", fe2o3=77.14285714285715 / 100, sio2=16.4 / 100,
        v2o5=0.45 / 100, cao=1.3 / 100, mgo=1.1 / 100, al2o3=0.9 / 100,
        tio2=0.0 / 100, mno=2.8 / 100, cr2o3=0.0 / 100,
        metallic_fe_convention=True, absorption_fixed=1111.2042634879963),
    "ore_block": CoolantSpec(
        "ore_block", "块矿", fe2o3=97.14285714285715 / 100, sio2=3.26 / 100,
        v2o5=0.001 / 100, cao=0.0305 / 100, mgo=0.8 / 100, al2o3=1.259 / 100,
        tio2=0.02 / 100, mno=0.14 / 100, cr2o3=0.0 / 100),
    "waste_slag_ball": CoolantSpec(
        "waste_slag_ball", "弃渣/铬渣球", fe2o3=87.97142857142858 / 100,
        sio2=3.26 / 100, v2o5=0.46 / 100, cao=1.21 / 100, mgo=1.266 / 100,
        al2o3=1.76 / 100, tio2=4.07 / 100, mno=0.18 / 100, cr2o3=0.2904 / 100,
        no_slag_dilution=True),
}
COOLANT_ORDER = ["pellet", "metal_fe", "ore_block", "waste_slag_ball"]


# ============================================================================
# 输入数据
# ============================================================================

@dataclass
class MetalAnalysis:
    """金属料化学成分 (百分数值, 如 C=4.3 表示 4.3%) 与温度"""
    C: float
    Si: float
    Mn: float
    P: float
    S: float
    V: float
    Cr: float
    Ti: float
    temp: float = 25.0

    def total(self) -> float:
        return self.C + self.Si + self.Mn + self.P + self.S + self.V + self.Cr + self.Ti


@dataclass
class PlantAInputs:
    """专家A模型输入 (默认值 = Excel 黄金用例: 基表!N14/15, 行15/16/17)"""
    iron_weight: float = 80000.0                 # 基表!N14 铁水装入量 kg
    pig_iron_weight: float = 0.0                 # 基表!N15 生铁块量 kg
    iron: MetalAnalysis = field(default_factory=lambda: MetalAnalysis(
        C=4.3, Si=0.215, Mn=0.18, P=0.132572156196944, S=0.0708828522920203,
        V=0.284, Cr=0.09, Ti=0.11, temp=1300.0))
    pig_iron: MetalAnalysis = field(default_factory=lambda: MetalAnalysis(
        C=4.2, Si=0.2, Mn=0.2, P=0.03, S=0.0708828522920203,
        V=0.06, Cr=0.0, Ti=0.0, temp=20.0))
    semi_steel: MetalAnalysis = field(default_factory=lambda: MetalAnalysis(
        C=3.485, Si=0.006, Mn=0.02, P=0.12225, S=0.0708828522920203,
        V=0.025, Cr=0.02, Ti=0.00833024691358023, temp=1370.0))
    fesilicon_kg: float = 34.5                   # 基表!F11 硅铁量 kg/炉
    # 冷料量: None 的品种按"热量富余/单位吸热"自动求解 (黄金用例仅球团自动)
    coolant_weights: Dict[str, Optional[float]] = field(default_factory=lambda: {
        "pellet": None, "metal_fe": 0.0, "ore_block": 0.0, "waste_slag_ball": 0.0})
    corrected: bool = False                      # True=修正口径(补 Q5 漏项)


# ============================================================================
# 一、物料平衡 (物料平衡推算表)
# ============================================================================

def material_balance(inp: PlantAInputs) -> Dict:
    mw = MW
    fixed_C = inp.iron.C * IRON_C_LAB_FACTOR                       # !C8
    iron_fixed = MetalAnalysis(
        C=fixed_C, Si=inp.iron.Si, Mn=inp.iron.Mn, P=inp.iron.P,
        S=inp.iron.S, V=inp.iron.V, Cr=inp.iron.Cr, Ti=inp.iron.Ti)
    # !C9: 生铁块 C 取铁水修正值 (专家口径)
    pig_fixed = MetalAnalysis(
        C=fixed_C, Si=inp.pig_iron.Si, Mn=inp.pig_iron.Mn, P=inp.pig_iron.P,
        S=inp.pig_iron.S, V=inp.pig_iron.V, Cr=inp.pig_iron.Cr, Ti=inp.pig_iron.Ti)

    total_metal = inp.iron_weight + inp.pig_iron_weight            # !F14
    f_iron = inp.iron_weight / total_metal                         # !D14
    f_pig = inp.pig_iron_weight / total_metal                      # !D15

    def avg(attr: str) -> float:
        return getattr(iron_fixed, attr) * f_iron + getattr(pig_fixed, attr) * f_pig

    ep = inp.semi_steel
    ox_pct = {k: avg(k) - getattr(ep, k) for k in
              ("C", "Si", "Mn", "P", "S", "V", "Cr", "Ti")}        # !C12..J12

    m = lambda pct: pct / 100.0 * total_metal                      # 氧化量 kg
    ox_m = {
        "Si": m(ox_pct["Si"]), "Mn": m(ox_pct["Mn"]), "Ti": m(ox_pct["Ti"]),
        "Cr": m(ox_pct["Cr"]), "V": m(ox_pct["V"]), "P": m(ox_pct["P"]),
        "C_CO": m(ox_pct["C"]) * CO_SHARE, "C_CO2": m(ox_pct["C"]) * CO2_SHARE,
    }
    o2 = {
        "Si": ox_m["Si"] * mw["O2_per_Si"], "Mn": ox_m["Mn"] * mw["O2_per_Mn"],
        "Ti": ox_m["Ti"] * mw["O2_per_Ti"], "Cr": ox_m["Cr"] * mw["O2_per_Cr"],
        "V": ox_m["V"] * mw["O2_per_V"], "P": ox_m["P"] * mw["O2_per_P"],
        "C_CO": ox_m["C_CO"] * mw["O2_per_C_CO"],
        "C_CO2": ox_m["C_CO2"] * mw["O2_per_C_CO2"],
    }
    prod = {
        "SiO2": ox_m["Si"] * mw["SiO2_per_Si"], "MnO": ox_m["Mn"] * mw["MnO_per_Mn"],
        "TiO2": ox_m["Ti"] * mw["TiO2_per_Ti"],
        "Cr2O3": ox_m["Cr"] * mw["Cr2O3_per_Cr"],
        "V2O5": ox_m["V"] * mw["V2O5_per_V"], "P2O5": ox_m["P"] * mw["P2O5_per_P"],
        "CO": ox_m["C_CO"] * mw["CO_per_C"], "CO2": ox_m["C_CO2"] * mw["CO2_per_C"],
    }

    # 炉衬侵蚀 (!L38)
    lining_kg = LINING_RATIO * total_metal
    lining_cao = lining_kg * LINING["CaO"]
    lining_mgo = lining_kg * LINING["MgO"]
    lining_sio2 = lining_kg * LINING["SiO2"]
    lining_al2o3 = lining_kg * LINING["Al2O3"]

    # 渣量: 非铁氧化物 / (1 - FeO% - Fe2O3%) (!E63)
    non_fe = (prod["V2O5"] + prod["TiO2"] + prod["Cr2O3"]
              + prod["SiO2"] + lining_sio2 + prod["P2O5"] + prod["MnO"]
              + lining_cao + lining_mgo + lining_al2o3)            # !E59
    slag_total = non_fe / (1 - SLAG_FEO - SLAG_FE2O3)              # !E63
    feo_mass = slag_total * SLAG_FEO                               # !E60
    fe2o3_mass = slag_total * SLAG_FE2O3                           # !E61
    ox_m["Fe_FeO"] = feo_mass * mw["Fe_per_FeO"]                   # !D27
    ox_m["Fe_Fe2O3"] = fe2o3_mass * mw["Fe_per_Fe2O3"]             # !D28
    o2["Fe_FeO"] = ox_m["Fe_FeO"] * mw["O2_per_Fe_FeO"]
    o2["Fe_Fe2O3"] = ox_m["Fe_Fe2O3"] * mw["O2_per_Fe_Fe2O3"]

    ox_total = sum(ox_m.values())                                  # !D29
    o2_total = sum(o2.values())                                    # !E29

    # 烟尘 (!表1.5): 氧耗按氧化物中氧的质量比 16/72 与 48/160
    dust = DUST_RATIO * total_metal                                # !C67
    dust_o2 = (dust * DUST_FEO * (16 / 72)
               + dust * DUST_FE2O3 * (48 / 160))                   # !C68
    dust_fe = (dust * DUST_FEO * mw["Fe_per_FeO"]
               + dust * DUST_FE2O3 * mw["Fe_per_Fe2O3"])           # !C69

    # 炉衬碳氧 (!表1.6)
    lining_co = lining_kg * LINING["C"] * CO_SHARE * mw["CO_per_C"]      # !C72
    lining_co2 = lining_kg * LINING["C"] * CO2_SHARE * mw["CO2_per_C"]   # !C73
    lining_o2 = lining_co * (16 / 28) + lining_co2 * (32 / 44)     # !E72/E73

    # 炉气 (!表1.7)
    co_mass = prod["CO"] + lining_co                               # !C77
    co2_mass = prod["CO2"] + lining_co2                            # !C78
    v_co = co_mass * 22.4 / 28
    v_co2 = co2_mass * 22.4 / 44

    # 自由氧/氮气: 复刻 Excel 二元线性方程组 (附表 C8:K13)
    rhs1 = (v_co + v_co2) * FREE_O2_PCT * 100
    rhs2 = (o2_total + dust_o2 + lining_o2) * 22.4 / 32 * (1 - O2_PURITY) * 100
    a11, a12, a21, a22 = 99.5, 0.5, 0.2, 99.8
    det = a11 * a22 - a12 * a21
    v_o2 = (rhs1 * a22 - a12 * rhs2) / det                         # !D79
    v_n2 = (a11 * rhs2 - a21 * rhs1) / det                         # !D80
    o2_free_mass = v_o2 * 32 / 22.4                                # !C79
    n2_mass = v_n2 * 28 / 22.4                                     # !C80

    # 实际氧耗 (!表1.8)
    o2_kg = o2_total + dust_o2 + o2_free_mass + n2_mass + lining_o2  # !C84
    o2_vol = ((o2_total + dust_o2 + o2_free_mass + lining_o2) * 22.4 / 32
              + n2_mass * 22.4 / 28)                               # !C85

    # 铁珠/喷溅/钢水 (!表1.9-1.11)
    beads = slag_total * SLAG_IRON_BEADS                           # !D89
    spitting = SPITTING_RATIO * total_metal                        # !D93
    steel = total_metal - (ox_total + dust_fe + beads + spitting)  # !D96

    income = inp.iron_weight + inp.pig_iron_weight + lining_kg + o2_kg
    gas_mass = co_mass + co2_mass + o2_free_mass + n2_mass         # !C81
    outlay = steel + slag_total + gas_mass + dust + beads + spitting

    return {
        "total_metal": total_metal, "iron_C_fixed": fixed_C,
        "iron_full_iron": inp.iron_weight * (1 - iron_fixed.total() / 100),  # !D113
        "ox_m": ox_m, "o2_total": o2_total, "prod": prod,
        "lining_kg": lining_kg, "non_fe_oxides": non_fe,
        "slag_total": slag_total, "feo_mass": feo_mass, "fe2o3_mass": fe2o3_mass,
        "slag_sio2": prod["SiO2"] + lining_sio2,                   # !E55
        "dust": dust, "dust_o2": dust_o2, "dust_fe": dust_fe,
        "lining_co": lining_co, "lining_co2": lining_co2, "lining_o2": lining_o2,
        "co_mass": co_mass, "co2_mass": co2_mass, "gas_mass": gas_mass,
        "gas_vol": v_co + v_co2 + v_o2 + v_n2,                     # !D81
        "v_o2_free": v_o2, "v_n2": v_n2,
        "o2_kg": o2_kg, "o2_vol": o2_vol,
        "beads": beads, "spitting": spitting, "steel": steel,
        "ox_total": ox_total,
        "balance_diff": income - outlay,                           # !G108
        "balance_diff_pct": (income - outlay) / outlay,            # !G109
    }


# ============================================================================
# 二、热量平衡 (2、热量平衡推算表)
# ============================================================================

def iron_freezing_point(iron: MetalAnalysis) -> float:
    """!C29: 1535 - (C×100 + Si×8 + Mn×5 + P×30 + S×25) - 7"""
    return 1535.0 - (iron.C * 100 + iron.Si * 8 + iron.Mn * 5
                     + iron.P * 30 + iron.S * 25) - 7


def steel_freezing_point(steel: MetalAnalysis) -> float:
    """!C30: 钢水 C 系数为 65 (≠铁水 100), 专家经验"""
    return 1535.0 - (steel.C * 65 + steel.Si * 8 + steel.Mn * 5
                     + steel.P * 30 + steel.S * 25) - 7


def heat_balance(inp: PlantAInputs, mat: Dict) -> Dict:
    cp_i, cp_s, cp_sl = CP["iron"], CP["steel"], CP["slag"]
    ep = inp.semi_steel
    tf_i = iron_freezing_point(MetalAnalysis(
        C=mat["iron_C_fixed"], Si=inp.iron.Si, Mn=inp.iron.Mn,
        P=inp.iron.P, S=inp.iron.S, V=0.0, Cr=0.0, Ti=0.0))
    tf_s = steel_freezing_point(ep)

    # 铁水物理热 (!C31, 仅计铁水, 生铁块物理热 Excel 未计)
    h_iron = inp.iron_weight * (cp_i["cp_s"] * (tf_i - AMBIENT_TEMP) + cp_i["L"]
                                + cp_i["cp_l"] * (inp.iron.temp - tf_i))

    ox = mat["ox_m"]
    heats = {
        "Si": ox["Si"] * DH_SI, "Mn": ox["Mn"] * DH_MN, "Ti": ox["Ti"] * DH_TI,
        "Cr": ox["Cr"] * DH_CR, "V": ox["V"] * DH_V, "P": ox["P"] * DH_P,
        "C_CO": ox["C_CO"] * DH_C_CO, "C_CO2": ox["C_CO2"] * DH_C_CO2,
        "Fe_FeO": ox["Fe_FeO"] * DH_FE_FEO,
        "Fe_Fe2O3": ox["Fe_Fe2O3"] * DH_FE_FE2O3,
        "SiO2_slag": mat["slag_sio2"] * DH_SIO2_SLAG,              # !E45
    }
    h_elements = sum(heats.values())                               # !E46

    # 烟尘氧化热 (!表2.5)
    h_dust = (mat["dust"] * DUST_FEO * FE_IN_FEO * DH_FE_FEO
              + mat["dust"] * DUST_FE2O3 * FE_IN_FE2O3 * DH_FE_FE2O3)
    # 炉衬碳氧化热 (!表2.6)
    h_lining_c = (mat["lining_co"] * (12 / 28) * DH_C_CO
                  + mat["lining_co2"] * (12 / 44) * DH_C_CO2)
    income = h_iron + h_elements + h_dust + h_lining_c             # !C61

    # 支出 (!表2.8)
    h_steel = mat["steel"] * (cp_s["cp_s"] * (tf_s - AMBIENT_TEMP) + cp_s["L"]
                              + cp_s["cp_l"] * (ep.temp - tf_s))
    t_slag = ep.temp - SLAG_TEMP_DELTA
    h_slag = mat["slag_total"] * (cp_sl["cp_l"] * (t_slag - AMBIENT_TEMP) + cp_sl["L"])
    h_gas = mat["gas_mass"] * CP["gas"]["cp_l"] * (GAS_TEMP - AMBIENT_TEMP)
    h_dust_ph = mat["dust"] * (CP["dust"]["cp_l"] * (GAS_TEMP - AMBIENT_TEMP)
                               + CP["dust"]["L"])
    bead_factor = (cp_s["cp_s"] * (tf_s - AMBIENT_TEMP) + cp_s["L"]
                   + cp_s["cp_l"] * (ep.temp - SLAG_TEMP_DELTA - tf_s))  # 渣中铁珠(终点-20)
    h_beads = mat["beads"] * bead_factor
    spit_factor = (cp_s["cp_s"] * (tf_s - AMBIENT_TEMP) + cp_s["L"]
                   + cp_s["cp_l"] * (SPIT_TEMP - tf_s))
    h_spit = mat["spitting"] * spit_factor
    h_other = income * OTHER_HEAT_LOSS                             # !C71
    outlay = h_steel + h_slag + h_gas + h_dust_ph + h_beads + h_spit + h_other

    return {
        "tf_iron": tf_i, "tf_steel": tf_s, "h_iron": h_iron,
        "heats": heats, "h_elements": h_elements, "h_dust_ox": h_dust,
        "h_lining_c": h_lining_c, "income": income,
        "h_steel": h_steel, "h_slag": h_slag, "h_gas": h_gas,
        "h_dust_ph": h_dust_ph, "h_beads": h_beads, "h_spit": h_spit,
        "h_other": h_other, "outlay": outlay,
        "surplus": income - outlay,                                # !G90
        "surplus_pct": (income - outlay) / income,                 # !G91
        "bead_factor": bead_factor,
    }


# ============================================================================
# 三、冷料边际响应 (3/4、冷料配吃表) —— 模型精华
# ============================================================================

def coolant_marginal(inp: PlantAInputs, heat: Dict) -> Dict[str, Dict]:
    """每 kg 冷料对物料/热平衡的边际影响 (Excel 以 1kg 为例推导, 表3.1/4.1)"""
    ep = inp.semi_steel
    chem_loss_coef = SLAG_FEO * FE_IN_FEO + SLAG_FE2O3 * FE_IN_FE2O3
    o2_slag_coef = SLAG_FEO * (16 / 72) + SLAG_FE2O3 * (48 / 160)
    heat_slag_per_kg = (CP["slag"]["cp_l"]
                        * (ep.temp - SLAG_TEMP_DELTA - AMBIENT_TEMP) + CP["slag"]["L"])
    steel_heat_per_kg = (CP["steel"]["cp_s"] * (heat["tf_steel"] - AMBIENT_TEMP)
                         + CP["steel"]["L"]
                         + CP["steel"]["cp_l"] * (ep.temp - heat["tf_steel"]))

    out: Dict[str, Dict] = {}
    for key, spec in COOLANTS.items():
        bring = 1.0 - spec.fe2o3                                   # 非Fe2O3 带入
        if spec.no_slag_dilution:                                  # Q2
            slag_up = bring
        else:
            slag_up = bring / (1 - SLAG_FEO - SLAG_FE2O3)
        if spec.metallic_fe_convention:                            # 金属铁: fe2o3 位即金属铁率
            fe_to_steel = spec.fe2o3                               # !D8 直接取
            beads_up = slag_up * (SLAG_IRON_BEADS / 100)           # Q1: D88%
        else:
            fe_to_steel = spec.fe2o3 * FE_IN_FE2O3                 # Fe2O3→Fe
            beads_up = slag_up * SLAG_IRON_BEADS                   # !D28
        chem_loss = slag_up * chem_loss_coef                       # !D10/D29
        steel_up = fe_to_steel - beads_up - chem_loss              # !E8/E27
        o2_release = spec.fe2o3 * (48 / 160)                       # Fe2O3 分解放氧
        o2_net = o2_release - slag_up * o2_slag_coef
        if spec.metallic_fe_convention:                            # Q3: 双重 /99.8%
            o2_down = o2_net / O2_PURITY / O2_PURITY
        else:
            o2_down = o2_net / O2_PURITY                           # !E30
        n2_down = o2_down * (1 - O2_PURITY)                        # !D33

        # 热量边际 (表4.1)
        h_in = (slag_up * (DH_FE_FEO * SLAG_FEO * FE_IN_FEO
                           + DH_FE_FE2O3 * SLAG_FE2O3 * FE_IN_FE2O3)  # Fe氧化放热 !C26
                + 1.0 * spec.sio2 * DH_SIO2_SLAG)                     # 成渣热 !C27
        h_out = (steel_up * steel_heat_per_kg                       # 钢水物理热 !E26
                 + slag_up * heat_slag_per_kg                       # 渣物理热 !E27
                 + beads_up * heat["bead_factor"])                  # 渣中铁珠热 !E28
        if not spec.metallic_fe_convention:
            h_out += spec.fe2o3 * FE_IN_FE2O3 * DH_FE_FE2O3         # Fe2O3 分解吸热 !E29
        h_out += h_in * OTHER_HEAT_LOSS                             # 其他热损 !E30
        out[key] = {
            "slag_up": slag_up, "steel_up": steel_up, "beads_up": beads_up,
            "o2_down": o2_down, "n2_down": n2_down,
            "h_in": h_in, "h_out": h_out,
            "absorption": (spec.absorption_fixed if spec.absorption_fixed
                           else h_out - h_in),                     # !I31 (Q6)
        }
    return out


def solve_coolants(inp: PlantAInputs, heat: Dict, marginal: Dict) -> Dict[str, float]:
    """确定各冷料量: 显式给定, 或按 热量富余/单位吸热 自动求解 (!H35)"""
    return {key: (heat["surplus"] / marginal[key]["absorption"] if w is None else w)
            for key, w in inp.coolant_weights.items()}


# ============================================================================
# 四、冷料后终态 + 钒平衡/原料标准
# ============================================================================

def after_coolant(inp: PlantAInputs, mat: Dict, heat: Dict,
                  marginal: Dict, weights: Dict[str, float]) -> Dict:
    steel_add = slag_add = beads_add = o2_cut = gas_add = 0.0
    h_income_add = h_outlay_replica = h_outlay_correct = 0.0
    for key, kg in weights.items():
        mg = marginal[key]
        steel_add += mg["steel_up"] * kg
        slag_add += mg["slag_up"] * kg
        beads_add += mg["beads_up"] * kg
        o2_cut += mg["o2_down"] * kg
        gas_add += mg["n2_down"] * kg
        h_income_add += mg["h_in"] * kg
        # 复刻口径: 球团的渣中铁珠热不计入支出 (Q5); 修正口径全计入
        bead_term = mg["beads_up"] * heat["bead_factor"] * kg
        h_outlay_replica += (mg["h_out"] * kg
                             - (bead_term if key == "pellet" else 0.0))
        h_outlay_correct += mg["h_out"] * kg

    steel2 = mat["steel"] + steel_add
    slag2 = mat["slag_total"] + slag_add
    beads2 = mat["beads"] + beads_add
    hot_metal_slag = inp.iron_weight * HOT_METAL_SLAG_RATIO         # 铁水带渣 !D106
    income2 = heat["income"] + h_income_add
    outlay_replica = heat["outlay"] + h_outlay_replica
    outlay_correct = heat["outlay"] + h_outlay_correct

    return {
        "steel": steel2, "slag": slag2, "beads": beads2,
        "spitting": mat["spitting"], "o2_kg": mat["o2_kg"] - o2_cut,
        "hot_metal_slag": hot_metal_slag,
        "income": income2,
        "outlay_replica": outlay_replica,
        "outlay": outlay_correct,
        "residual_replica": income2 - outlay_replica,               # !H99 (含 Q5 漏项)
        "residual": income2 - outlay_correct,                       # 修正口径
        "residual_pct": (income2 - outlay_correct) / outlay_correct,
        "coolant_weights": weights,
        "delta": {"steel": steel_add, "slag": slag_add, "beads": beads_add,
                  "o2": -o2_cut, "gas": gas_add},
    }


def vanadium_and_product_balance(inp: PlantAInputs, mat: Dict, after: Dict) -> Dict:
    """钒元素平衡 + 吨半钢原料标准 + 精钒渣成分反算 (提钒转炉原料标准表)"""
    ep = inp.semi_steel
    den = after["hot_metal_slag"] + after["slag"]                   # !(G106+G107)
    w = after["coolant_weights"]

    def kg(key: str) -> float:
        return w.get(key, 0.0) or 0.0

    # --- 钒平衡 ---
    v_in_iron = inp.iron_weight * (inp.iron.V / 100)                # !K22 (用化验V)
    v_in_coolant = sum(COOLANTS[k].v2o5 * (102 / 182) * kg(k)
                       for k in COOLANT_ORDER)                      # !K24
    v_in_total = v_in_iron + v_in_coolant                           # !K30
    # 渣中 V (!N23): 铁水氧化V + 冷料净带入V(扣除带入铁量的残V) × 0.965
    coolant_v_net = sum((COOLANTS[k].v2o5 * (102 / 182) - ep.V / 100) * kg(k)
                        for k in COOLANT_ORDER)
    v_out_slag = (mat["ox_m"]["V"] + coolant_v_net) * V_IN_SLAG_FACTOR
    v_out_semi = after["steel"] * (ep.V / 100)                      # !N22
    v_out_beads = after["beads"] * (ep.V / 100)                     # !N24
    v_out_spit = after["spitting"] * (inp.iron.V / 100)             # !N25 (用铁水V%, 专家口径)
    v_out_dust = v_in_total - (v_out_semi + v_out_slag + v_out_beads + v_out_spit)  # !N26
    v_recovery = v_out_slag / v_in_total                            # !N31

    # --- 吨半钢原料标准 ---
    std_iron = inp.iron_weight / after["steel"]                     # !E4
    std_pellet = kg("pellet") / after["steel"]                      # !E8
    std_fesilicon = inp.fesilicon_kg / after["steel"] * 1000        # !E13 kg/t
    slag_std = ((after["hot_metal_slag"] + after["slag"] + after["beads"])
                / after["steel"] * V_RECOVERY_SLAG_FACTOR)          # !E15
    std_sludge = (mat["dust"] * SLUDGE_FACTOR_A / after["steel"]
                  / SLUDGE_FACTOR_B + SLUDGE_ADD)                   # !E16

    # --- 精钒渣成分反算 (!F20..F29) ---
    def comp(mass: float, coolant_attr: Optional[str] = None) -> float:
        total = mass
        if coolant_attr:
            total += sum(getattr(COOLANTS[k], coolant_attr) * kg(k)
                         for k in COOLANT_ORDER)
        return total / den * 100

    slag_v2o5_mass = mat["prod"]["V2O5"] + sum(
        (COOLANTS[k].v2o5 - ep.V * V2O5_PER_V / 100) * kg(k)
        for k in COOLANT_ORDER)
    grade = {
        "V2O5": slag_v2o5_mass / den * 100,                        # !F20 ★核心输出
        "CaO": comp(mat["lining_kg"] * LINING["CaO"], "cao"),      # !F21(Excel为定值2, 此为计算口径)
        "MgO": comp(mat["lining_kg"] * LINING["MgO"], "mgo"),      # !F22
        "TiO2": comp(mat["prod"]["TiO2"], "tio2"),                 # !F23
        "SiO2": comp(mat["slag_sio2"], "sio2"),                    # !F24
        "P2O5": comp(mat["prod"]["P2O5"]),                         # !F25
        "MnO": comp(mat["prod"]["MnO"], "mno"),                    # !F26
        "Al2O3": comp(mat["lining_kg"] * LINING["Al2O3"], "al2o3"),  # !F27
        "Cr2O3": comp(mat["prod"]["Cr2O3"], "cr2o3"),              # !F28
    }
    tfe_mass = after["slag"] * (SLAG_FEO * FE_IN_FEO + SLAG_FE2O3 * FE_IN_FE2O3)
    grade["TFe"] = tfe_mass / den * 100 * TFE_FACTOR               # !F29

    return {
        "v_balance": {
            "in_iron": v_in_iron, "in_coolant": v_in_coolant, "in_total": v_in_total,
            "out_semi": v_out_semi, "out_slag": v_out_slag,
            "out_beads": v_out_beads, "out_spit": v_out_spit, "out_dust": v_out_dust,
            "recovery_pct": v_recovery * 100,
        },
        "standard_per_t_semi": {
            "iron_t": std_iron, "pellet_t": std_pellet,
            "fesilicon_kg": std_fesilicon, "vslag_t": slag_std,
            "sludge_t": std_sludge,
        },
        "slag_grade": grade,
    }


# ============================================================================
# 五、顶层编排
# ============================================================================

@dataclass
class PlantAResults:
    material: Dict
    heat: Dict
    marginal: Dict
    after: Dict
    product: Dict

    @property
    def v2o5_grade(self) -> float:
        """精钒渣 V2O5 品位 % —— 模型核心输出"""
        return self.product["slag_grade"]["V2O5"]


def run_plant_a_model(inp: Optional[PlantAInputs] = None) -> PlantAResults:
    inp = inp or PlantAInputs()
    mat = material_balance(inp)
    heat = heat_balance(inp, mat)
    marginal = coolant_marginal(inp, heat)
    weights = solve_coolants(inp, heat, marginal)
    after = after_coolant(inp, mat, heat, marginal, weights)
    product = vanadium_and_product_balance(inp, mat, after)
    return PlantAResults(mat, heat, marginal, after, product)


def predict_v2o5_grade(iron_C: float, iron_Si: float, iron_V: float,
                       iron_T: float = 1300.0,
                       iron_weight: float = 80000.0) -> float:
    """给定铁水条件预测精钒渣 V2O5 品位 (品位归因场景, 对应工作表1 的用法)"""
    base = PlantAInputs()
    base.iron_weight = iron_weight
    base.iron = MetalAnalysis(
        C=iron_C, Si=iron_Si, Mn=base.iron.Mn, P=base.iron.P, S=base.iron.S,
        V=iron_V, Cr=base.iron.Cr, Ti=base.iron.Ti, temp=iron_T)
    return run_plant_a_model(base).v2o5_grade


if __name__ == "__main__":
    r = run_plant_a_model()
    print(f"铁水C修正       : {r.material['iron_C_fixed']:.4f} %")
    print(f"渣总量          : {r.material['slag_total']:.1f} kg")
    print(f"物料收支差      : {r.material['balance_diff_pct']*100:.4f} %")
    print(f"热量富余        : {r.heat['surplus']/1e6:.2f} MJ ({r.heat['surplus_pct']*100:.2f}%)")
    print(f"球团配吃量      : {r.after['coolant_weights']['pellet']:.1f} kg")
    print(f"冷料后钢水      : {r.after['steel']:.1f} kg")
    print(f"热平衡差(复刻Q5): {r.after['residual_replica']/1e3:.2f} kJ")
    print(f"热平衡差(修正)  : {r.after['residual']:.4f} kJ ({r.after['residual_pct']*100:.6f}%)")
    print(f"钒回收率        : {r.product['v_balance']['recovery_pct']:.2f} %")
    print(f"精钒渣 V2O5     : {r.v2o5_grade:.3f} %")
