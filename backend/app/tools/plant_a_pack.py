# -*- coding: utf-8 -*-
"""VERO 知识包加载器 (Knowledge Pack Loader)

加载厂级 YAML 知识包 (如 knowledge/packs/plant_a/base.yaml), 并提供:
1. load_pack()           —— 读取并做 schema 基本校验
2. assert_pack_matches() —— 校验包内常数与复现代码常数一致 (防"两处真相")
3. coolant_specs_from_pack() —— 从包构建冷料规格对象

知识包即"单一事实来源"的种子: 未来 initial_charge / equilibrium 等引擎
的厂级参数都应从这里取, 而不是各自硬编码。
"""

from __future__ import annotations

import os
from typing import Dict, List

import yaml

from .plant_a_reference import COOLANTS, CoolantSpec

DEFAULT_PACK = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "knowledge", "packs", "plant_a", "base.yaml")

INDUSTRY_PACK = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "knowledge", "packs", "industry", "base.yaml")

# 部署厂 (默认专家B; 可用环境变量 VERO_PLANT 覆盖)。产品本身面向行业, 厂级仅作参数覆盖源。
DEFAULT_PLANT = os.environ.get("VERO_PLANT", "plant_b")

VALID_SCOPES = {"industry", "plant", "workshop", "furnace"}


def load_pack(path: str = DEFAULT_PACK) -> Dict:
    # 厂级知识包属保密资产, 允许不随仓库分发; 缺失时降级为「空覆盖集」, 计算以行业基线为准。
    if not os.path.exists(path):
        return {
            "schema": "vero.knowledge-pack/v1",
            "pack": {"scope": "plant", "plant": "plant_a"},
            "parameters": {},
            "known_conflicts": [],
            "_missing": True,
        }
    with open(path, "r", encoding="utf-8") as f:
        pack = yaml.safe_load(f)
    meta = pack.get("pack", {})
    assert pack.get("schema") == "vero.knowledge-pack/v1", "未知知识包 schema"
    assert meta.get("scope") in VALID_SCOPES, f"非法 scope: {meta.get('scope')}"
    return pack


def _p(pack: Dict, *path):
    """按路径取参数: _p(pack, 'thermo', 'dh', 'V', 'value')"""
    node = pack["parameters"]
    for key in path:
        node = node[key]
    return node


def pack_discrepancies(pack: Dict) -> List[str]:
    """逐项核对包内常数与 plant_a_reference 模块常数, 返回不一致清单"""
    from app.tools import plant_a_reference as ref
    issues: List[str] = []

    # 知识包缺失/为空 (保密资产未随仓库分发) 时, 无可核对项, 直接返回空清单。
    if not pack.get("parameters"):
        return issues

    def check(name: str, pack_value, ref_value, tol: float = 1e-9):
        if ref_value is None or pack_value is None:
            return
        if isinstance(ref_value, (int, float)) and isinstance(pack_value, (int, float)):
            if abs(pack_value - ref_value) > tol * max(1.0, abs(ref_value)):
                issues.append(f"{name}: 包={pack_value} 代码={ref_value}")

    cc = pack["parameters"]["composition_corrections"]
    check("iron_c_lab_factor", cc["iron_c_lab_factor"]["value"], ref.IRON_C_LAB_FACTOR)
    check("hot_metal_slag_ratio", cc["hot_metal_slag_ratio"]["value"], ref.HOT_METAL_SLAG_RATIO)

    oa = pack["parameters"]["oxidation_allocation"]
    check("co_share", oa["co_share"]["value"], ref.CO_SHARE)
    check("co2_share", oa["co2_share"]["value"], ref.CO2_SHARE)
    check("slag_feo", oa["slag_feo"]["value"], ref.SLAG_FEO)
    check("slag_fe2o3", oa["slag_fe2o3"]["value"], ref.SLAG_FE2O3)
    check("slag_iron_beads", oa["slag_iron_beads"]["value"], ref.SLAG_IRON_BEADS)
    check("spitting_ratio", oa["spitting_ratio"]["value"], ref.SPITTING_RATIO)
    check("dust_ratio", oa["dust_ratio"]["value"], ref.DUST_RATIO)
    check("dust_feo", oa["dust_feo"]["value"], ref.DUST_FEO)
    check("dust_fe2o3", oa["dust_fe2o3"]["value"], ref.DUST_FE2O3)
    check("lining_ratio", oa["lining_ratio"]["value"], ref.LINING_RATIO)
    check("free_o2_pct", oa["free_o2_pct"]["value"], ref.FREE_O2_PCT)
    check("o2_purity", oa["o2_purity"]["value"], ref.O2_PURITY)

    th = pack["parameters"]["thermo"]
    check("dh.Si", th["dh"]["Si"]["value"], ref.DH_SI)
    check("dh.Mn", th["dh"]["Mn"]["value"], ref.DH_MN)
    check("dh.Ti", th["dh"]["Ti"]["value"], ref.DH_TI, tol=1e-4)
    check("dh.V", th["dh"]["V"]["value"], ref.DH_V)
    check("dh.P", th["dh"]["P"]["value"], ref.DH_P)
    check("dh.C_CO", th["dh"]["C_CO"]["value"], ref.DH_C_CO)
    check("dh.C_CO2", th["dh"]["C_CO2"]["value"], ref.DH_C_CO2)
    check("dh.Fe_FeO", th["dh"]["Fe_FeO"]["value"], ref.DH_FE_FEO)
    check("dh.Fe_Fe2O3", th["dh"]["Fe_Fe2O3"]["value"], ref.DH_FE_FE2O3)
    check("dh.Cr", th["dh"]["Cr"]["value"], ref.DH_CR)
    check("dh.SiO2_slag", th["dh"]["SiO2_slag"]["value"], ref.DH_SIO2_SLAG)
    check("cp.iron.cp_s", th["cp"]["iron"]["cp_s"], ref.CP["iron"]["cp_s"])
    check("cp.steel.cp_s", th["cp"]["steel"]["cp_s"], ref.CP["steel"]["cp_s"])

    ef = pack["parameters"]["empirical_formulas"]
    check("slag_temp_delta_c", ef["slag_temp_delta_c"]["value"], ref.SLAG_TEMP_DELTA)
    check("gas_temp_c", ef["gas_temp_c"]["value"], ref.GAS_TEMP)
    check("spit_temp_c", ef["spit_temp_c"]["value"], ref.SPIT_TEMP)
    check("other_heat_loss_pct", ef["other_heat_loss_pct"]["value"] / 100.0, ref.OTHER_HEAT_LOSS)

    pc = pack["parameters"]["product_conversion"]
    check("v_recovery_slag_factor", pc["v_recovery_slag_factor"]["value"], ref.V_RECOVERY_SLAG_FACTOR)
    check("v_in_slag_factor", pc["v_in_slag_factor"]["value"], ref.V_IN_SLAG_FACTOR)
    check("tfe_factor", pc["tfe_factor"]["value"], ref.TFE_FACTOR)

    # 冷料规格
    specs = pack["parameters"]["coolant_marginal"]["specs"]
    for key, spec in COOLANTS.items():
        ys = specs.get(key, {})
        check(f"coolant.{key}.fe2o3", ys.get("fe2o3"), spec.fe2o3)
        check(f"coolant.{key}.sio2", ys.get("sio2"), spec.sio2)
        check(f"coolant.{key}.v2o5", ys.get("v2o5"), spec.v2o5)
    return issues


def coolant_specs_from_pack(pack: Dict) -> Dict[str, CoolantSpec]:
    """从知识包构建冷料规格 (未来由包驱动模型, 替代代码内硬编码)"""
    specs = pack["parameters"]["coolant_marginal"]["specs"]
    out = {}
    for key, ys in specs.items():
        out[key] = CoolantSpec(
            key=key, label=key, fe2o3=ys["fe2o3"], sio2=ys["sio2"], v2o5=ys["v2o5"])
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并: 厂级包覆盖行业基线同键值, 非重叠键并存。"""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


#: 最近一次 resolve_parameters 的降级状态（供 UI/引擎显式标注"已降级"，禁止降级值进 KPI 合同轨）
RESOLVE_STATUS: Dict = {
    "plant": None,
    "plant_pack_loaded": False,
    "degraded": False,
    "message": "尚未执行 resolve_parameters",
}


def last_resolve_status() -> Dict:
    """返回最近一次 resolve_parameters 的状态（含降级标记）。"""
    return dict(RESOLVE_STATUS)


def resolve_parameters(plant: str | None = None) -> Dict:
    """
    按 scope 分层合并参数: 行业基线(industry, 行业通用规则) → 厂级包(plant, 覆盖/补充)。

    - plant=None 时使用 DEFAULT_PLANT (默认 plant_b, 可用 VERO_PLANT 覆盖)。
    - 返回合并后的 parameters dict, 供 initial_charge / lance_profile 等引擎统一取值。
    单一事实来源: 行业基线定「行业通用逻辑」, 厂级包定「厂级参数值」。

    降级语义（显式，非静默）: 厂级包缺失时不崩溃（厂级包允许不随仓库分发），
    回退为行业基线单层，并更新 RESOLVE_STATUS.degraded=True —— 调用方（引擎/UI）
    必须读取 last_resolve_status() 并在输出中标注"已降级"。
    """
    with open(INDUSTRY_PACK, "r", encoding="utf-8") as f:
        industry = yaml.safe_load(f)
    assert industry.get("schema") == "vero.knowledge-pack/v1", "未知知识包 schema"
    assert industry["pack"]["scope"] == "industry", "期望行业基线 scope=industry"

    merged = industry["parameters"]
    target = plant or DEFAULT_PLANT
    packs_dir = os.path.dirname(os.path.dirname(INDUSTRY_PACK))  # knowledge/packs
    ppath = os.path.join(packs_dir, target, "base.yaml")
    if os.path.exists(ppath):
        with open(ppath, "r", encoding="utf-8") as f:
            plant_pack = yaml.safe_load(f)
        assert plant_pack.get("schema") == "vero.knowledge-pack/v1", "未知知识包 schema"
        merged = _deep_merge(merged, plant_pack["parameters"])
        RESOLVE_STATUS.update(
            plant=target, plant_pack_loaded=True, degraded=False,
            message=f"厂级包 {target} 已加载（行业基线打底 + 厂级覆盖）")
    else:
        RESOLVE_STATUS.update(
            plant=target, plant_pack_loaded=False, degraded=True,
            message=f"厂级包缺失: {ppath}（厂级包允许不随仓库分发）——已降级为行业基线单层取值，"
                    f"输出必须显式标注「已降级」且禁止用于 KPI 合同轨")
    return merged


if __name__ == "__main__":
    pack = load_pack()
    if pack.get("_missing"):
        print("⚠️ 厂级知识包（plant_a）缺失——属保密资产，允许不随仓库分发。")
        print("   计算走行业基线 + 当前厂级包（resolve_parameters），包/代码一致性核对跳过。")
    else:
        meta = pack["pack"]
        print(f"知识包: {meta.get('name')} v{meta.get('version')} (scope={meta.get('scope')}, status={meta.get('status')})")
        issues = pack_discrepancies(pack)
        n = sum(len(v) if isinstance(v, dict) else 1 for v in pack["parameters"].values())
        if issues:
            print(f"⚠️ 发现 {len(issues)} 处包/代码不一致:")
            for i in issues:
                print("  -", i)
        else:
            print(f"✅ 包内常数与复现代码完全一致 ({n} 类参数)")
        print(f"已知冲突清单: {len(pack.get('known_conflicts') or [])} 条")
