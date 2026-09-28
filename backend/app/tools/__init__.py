# -*- coding: utf-8 -*-
"""
VERO 「岗位能力包」最小实现: SKILL_REGISTRY 技能注册表

设计要点
--------
1. **惰性导入**: 注册表只在声明层记录 `module / attr`, 真正的 import 发生在技能
   首次被调用时 (`_lazy_func`)。因此 `import app.tools` 不会拉起 numpy / scipy
   等重型依赖, 也不会因为某个技能模块损坏而导致整个包 import 失败。
2. **注册容错**: 每条注册都包在 try/except 里, 失败只 warn 不抛出。
3. **确定性**: 注册的函数全部是确定性数值工具; 本模块不调用 LLM 做任何数值计算。
4. **只决策不执行**: 本注册表中的技能只产出建议/诊断, 不含任何写 DCS/PLC 设定值的路径。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import (
    CoolantRecommendation,
    CriticalTempResult,
    DiagnoseLowYieldResult,
    InitialChargeInputs,
    InitialChargeResult,
    IronInitialAnalysis,
    LanceProfile,
    ProcessData,
    SimulationInputs,
    SimulationResult,
    SlagAnalysis,
)

logger = logging.getLogger(__name__)

# ============================================================================
# 输入模型: 供 get_openai_tools() 生成 JSON Schema (OpenAI / DeepSeek function calling)
# 说明: 已在 schemas.py 里的模型直接复用; 关键字参数风格的技能在此补一层薄封装。
# ============================================================================


class LanceProfileInputs(BaseModel):
    si_content_pct: float = Field(..., ge=0.0, le=5.0, description="铁水硅含量，%")


class CriticalTempInputs(BaseModel):
    v_content_pct: float | None = Field(default=None, ge=0.0, le=5.0, description="熔池钒含量，%")
    current_temp_c: float | None = Field(default=None, ge=800.0, le=1800.0, description="当前熔池温度，℃")


class DiagnoseQualityInputs(BaseModel):
    slag: SlagAnalysis = Field(..., description="炉后渣样分析")
    process: ProcessData = Field(..., description="过程数据（一罐到底/终点温度/枪位等）")
    iron_analysis: IronInitialAnalysis | None = Field(default=None, description="铁水初始成分（可选）")


class KnowledgePackQueryInputs(BaseModel):
    param_path: str = Field(
        default="",
        description="点分参数路径，如 'l1_charge.target_temp_c.value'；留空则返回顶层参数分组键列表",
    )
    plant: str | None = Field(default=None, description="厂级包名（默认 plant_b，可传 plant_a/industry 等）")


class EmptyInputs(BaseModel):
    """无入参技能（如 list_conflicts）的占位 schema。"""


# ============================================================================
# 知识包工具（新增技能）：把知识包查询/冲突清单暴露为可被 Agent 调用的"能力"
# ============================================================================


def query_knowledge_pack(param_path: str = "", plant: str | None = None) -> dict[str, Any]:
    """
    查询知识包参数（单一事实来源）。参数按「行业基线(industry) → 厂级包(默认 plant_b)」合并。

    - param_path 为空: 返回顶层参数分组键列表
    - param_path 命中叶子节点: 返回 {"found": True, "value": ..., "unit":..., "source":...}
    - 未命中: 返回 {"found": False, "available_keys": [...]}
    """
    from .plant_a_pack import resolve_parameters  # 惰性导入（yaml 仅在调用时加载）

    merged = resolve_parameters(plant)
    node: Any = merged
    for key in [k for k in param_path.split(".") if k]:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return {
                "param_path": param_path,
                "found": False,
                "value": None,
                "available_keys": sorted(node.keys()) if isinstance(node, dict) else None,
            }

    if isinstance(node, dict) and "value" in node:
        return {
            "param_path": param_path,
            "found": True,
            "value": node.get("value"),
            "unit": node.get("unit"),
            "source": node.get("source"),
            "note": node.get("note"),
        }

    return {
        "param_path": param_path,
        "found": True,
        "value": node,
        "available_keys": sorted(node.keys()) if isinstance(node, dict) else None,
    }


def list_conflicts() -> dict[str, Any]:
    """
    列出知识包内部的已知冲突（known_conflicts）以及「包内常数 vs 复现代码常数」的不一致项。
    用于人工/仲裁环节判断某条建议是否踩在文献冲突区间上。
    """
    from .plant_a_pack import load_pack, pack_discrepancies  # 惰性导入

    pack = load_pack()
    meta = pack.get("pack", {})
    issues = pack_discrepancies(pack)
    known = pack.get("known_conflicts", []) or []
    return {
        "pack": meta.get("name"),
        "pack_version": meta.get("version"),
        "known_conflicts": known,
        "known_conflict_count": len(known),
        "discrepancies": issues,
        "discrepancy_count": len(issues),
    }


# ============================================================================
# SkillSpec
# ============================================================================


class SkillSpec(BaseModel):
    """岗位能力包中的一个「技能」描述。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="技能唯一名（用于 LLM 意图路由 / 事件重算）")
    version: str = Field(default="0.1.0", description="技能版本，写入 HandoffEnvelope.skill_versions")
    func: Callable[..., Any] = Field(..., description="可调用对象（惰性包装，首次调用时才 import 实现模块）")
    description: str = Field(..., description="技能说明，直接作为 function-calling 的 description")
    input_schema: Any = Field(
        default=None,
        description="输入模型：pydantic model 类，或 'module:Attr' 形式的惰性引用字符串",
    )
    output_schema: Any = Field(
        default=None,
        description="输出模型：pydantic model 类 / Dict[str, Any] 等描述性标注",
    )
    knowledge_pack_deps: List[str] = Field(
        default_factory=list, description="该技能依赖的知识包（用于版本溯源）")
    category: str = Field(default="general", description="技能分类（岗位能力包分组）")
    call_style: Literal["model", "kwargs"] = Field(
        default="model", description="调用约定：model=传入单个 pydantic 入参对象；kwargs=按字段展开传参")
    module: str = Field(default="", description="实现模块（惰性导入用）")
    attr: str = Field(default="", description="实现函数名（惰性导入用）")


# ============================================================================
# 惰性导入工具
# ============================================================================


def _lazy_func(module: str, attr: str) -> Callable[..., Any]:
    """返回一个惰性包装：首次调用时才 import module 并取 attr。"""

    def _wrapped(*args, **kwargs):
        mod = importlib.import_module(module)
        return getattr(mod, attr)(*args, **kwargs)

    _wrapped.__name__ = attr
    _wrapped.__qualname__ = f"{module}.{attr}"
    _wrapped.__doc__ = f"[lazy] {module}.{attr}(...) —— 首次调用时惰性导入"
    return _wrapped


_InputRef = Dict[str, str]  # 仅作类型别名说明

#: 声明式注册表：真正的函数 import 发生在调用时；schema 引用解析发生在 get_openai_tools() 时。
_SKILL_DECLARATIONS: List[Dict[str, Any]] = [
    {
        "name": "calculate_initial_charge",
        "version": "0.1.0",
        "module": "app.tools.initial_charge",
        "attr": "calculate_initial_charge",
        "description": (
            "L1 配料计算：按铁水重量/温度/成分与目标终点温度，输出开吹配料（冷却剂）建议、"
            "预计总氧量、预计渣量与 V/(Si+Ti) 判据。仅产出建议，不下发任何控制设定值。"
        ),
        "input_schema": InitialChargeInputs,
        "output_schema": InitialChargeResult,
        "knowledge_pack_deps": ["industry", "plant_b"],
        "category": "charge",
        "call_style": "model",
    },
    {
        "name": "recommend_lance_profile",
        "version": "0.1.0",
        "module": "app.tools.lance_profile",
        "attr": "recommend_lance_profile",
        "description": (
            "枪位曲线推荐：按铁水 Si 含量输出「低-高-低」或「全程低枪位」模式及分段枪位(mm)。"
            "仅产出建议，不下发任何控制设定值。"
        ),
        "input_schema": LanceProfileInputs,
        "output_schema": LanceProfile,
        "knowledge_pack_deps": ["industry", "plant_b"],
        "category": "lance",
        "call_style": "kwargs",
    },
    {
        "name": "simulate_blow_path",
        "version": "0.1.0",
        "module": "app.tools.kinetics_simulator",
        "attr": "simulate_blow_path",
        "description": (
            "L2 动力学仿真：给定初始成分/温度/配方/供氧强度，推演熔池温度与 C/Si/V/Ti 轨迹，"
            "给出碳钒转化点(Tc)到达时间与前瞻性操作建议。离线推演，不参与闭环控制。"
        ),
        "input_schema": SimulationInputs,
        "output_schema": SimulationResult,
        "knowledge_pack_deps": [],
        "category": "simulation",
        "call_style": "model",
    },
    {
        "name": "calculate_thermal_balance",
        "version": "0.1.0",
        "module": "app.tools.thermal_balance",
        "attr": "calculate_thermal_balance",
        "description": (
            "热平衡计算（达涅利 SDM 四大平衡）：按铁水条件/废钢/目标出钢温度，"
            "计算热盈余并给出冷却剂类型与 kg/t 建议。仅产出建议。"
        ),
        "input_schema": "app.tools.thermal_balance:ThermalBalanceInputs",
        "output_schema": CoolantRecommendation,
        "knowledge_pack_deps": [],
        "category": "thermal",
        "call_style": "model",
    },
    {
        "name": "calculate_equilibrium_state",
        "version": "0.1.0",
        "module": "app.tools.equilibrium_model",
        "attr": "calculate_equilibrium_state",
        "description": (
            "热力学平衡模型（物料/氧/渣/热 四大平衡）：给定初始条件与供氧，"
            "求解终点成分、终渣成分与终点温度，用于与动力学仿真交叉验证。"
        ),
        "input_schema": SimulationInputs,
        "output_schema": Dict[str, Any],
        "knowledge_pack_deps": [],
        "category": "equilibrium",
        "call_style": "model",
    },
    {
        "name": "predict_critical_temp",
        "version": "0.1.0",
        "module": "app.tools.critical_temp",
        "attr": "predict_critical_temp",
        "description": (
            "临界温度预测：碳钒转化温度 Tc（基准 1361℃，来自 industry 包 CF-007 的吉布斯推导），"
            "可按熔池钒含量微调，并给出当前温度距临界点的余量 margin_c。"
        ),
        "input_schema": CriticalTempInputs,
        "output_schema": CriticalTempResult,
        "knowledge_pack_deps": ["industry"],
        "category": "thermal",
        "call_style": "kwargs",
    },
    {
        "name": "diagnose_process_quality",
        "version": "0.1.0",
        "module": "app.tools.diagnose_process_quality",
        "attr": "diagnose_process_quality",
        "description": (
            "炉后质量诊断：基于渣样与过程数据诊断钒渣品位偏低、严重碳氧化、喷溅等问题，"
            "输出带机理根因与证据的 findings。仅产出诊断结论。"
        ),
        "input_schema": DiagnoseQualityInputs,
        "output_schema": DiagnoseLowYieldResult,
        "knowledge_pack_deps": ["industry"],
        "category": "diagnosis",
        "call_style": "kwargs",
    },
    {
        "name": "query_knowledge_pack",
        "version": "0.1.0",
        "func": query_knowledge_pack,
        "description": (
            "查询知识包参数（单一事实来源）：按点分路径取「行业基线 → 厂级包」合并后的参数值，"
            "返回 value/unit/source。用于回答'这个系数从哪来'。param_path 留空返回顶层分组键。"
        ),
        "input_schema": KnowledgePackQueryInputs,
        "output_schema": Dict[str, Any],
        "knowledge_pack_deps": ["industry", "plant_b"],
        "category": "knowledge",
        "call_style": "kwargs",
    },
    {
        "name": "list_conflicts",
        "version": "0.1.0",
        "func": list_conflicts,
        "description": (
            "列出知识包已知冲突（known_conflicts）与「包内常数 vs 复现代码常数」的不一致项，"
            "用于判断建议是否落在文献冲突区间。"
        ),
        "input_schema": EmptyInputs,
        "output_schema": Dict[str, Any],
        "knowledge_pack_deps": ["plant_a"],
        "category": "knowledge",
        "call_style": "kwargs",
    },
]


SKILL_REGISTRY: Dict[str, SkillSpec] = {}


def _build_registry() -> None:
    """按声明表构建注册表；单条失败只 warn，不影响整体 import。"""
    for decl in _SKILL_DECLARATIONS:
        name = decl.get("name", "<unknown>")
        try:
            payload = dict(decl)
            module = payload.get("module", "")
            attr = payload.get("attr", "")
            if module and attr:
                payload["func"] = _lazy_func(module, attr)
            elif "func" not in payload:
                raise ValueError(f"技能 {name} 既无 module/attr 也无 func")
            SKILL_REGISTRY[name] = SkillSpec(**payload)
        except Exception as exc:  # pragma: no cover - 注册容错
            logger.warning("技能注册失败，已跳过: %s (%s: %s)", name, type(exc).__name__, exc)


_build_registry()


# ============================================================================
# 查询 API
# ============================================================================


def get_skill(name: str) -> Optional[SkillSpec]:
    """按名取技能；不存在返回 None。"""
    return SKILL_REGISTRY.get(name)


def list_skills(category: Optional[str] = None) -> List[SkillSpec]:
    """列出技能；可按 category 过滤。"""
    specs = list(SKILL_REGISTRY.values())
    if category:
        specs = [s for s in specs if s.category == category]
    return specs


def list_categories() -> List[str]:
    return sorted({s.category for s in SKILL_REGISTRY.values()})


def resolve_input_model(spec: SkillSpec) -> Optional[type[BaseModel]]:
    """解析 input_schema：支持直接的 model 类或 'module:Attr' 惰性引用。"""
    schema = spec.input_schema
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema
    if isinstance(schema, str) and ":" in schema:
        module, attr = schema.split(":", 1)
        try:
            obj = getattr(importlib.import_module(module), attr)
            if isinstance(obj, type) and issubclass(obj, BaseModel):
                return obj
        except Exception as exc:
            logger.warning("解析入参模型失败 %s: %s", schema, exc)
            return None
    return None


def get_openai_tools(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    返回 OpenAI / DeepSeek function-calling 格式的 tools 数组，供 LLM 意图路由使用。

    形如:
        [{"type": "function",
          "function": {"name": ..., "description": ..., "parameters": <JSON Schema>}}]

    解析失败的技能会被跳过并 warn，不会污染整个数组。
    """
    tools: List[Dict[str, Any]] = []
    for spec in list_skills(category):
        model = resolve_input_model(spec)
        if model is None:
            logger.warning("技能 %s 缺少可用入参 schema，未导出到 tools", spec.name)
            continue
        try:
            parameters = model.model_json_schema()
        except Exception as exc:  # pragma: no cover
            logger.warning("技能 %s 的入参 schema 生成失败: %s", spec.name, exc)
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": f"[v{spec.version}] {spec.description}",
                    "parameters": parameters,
                },
            }
        )
    return tools


def invoke_skill(name: str, payload: Optional[dict[str, Any]] = None, **kwargs) -> Any:
    """
    统一调用入口：屏蔽不同技能的入参约定（model / kwargs）。

    - 传入 dict 会先经入参 pydantic 模型校验（保证进入确定性工具的数值合法）
    - 返回值即技能的确定性输出（pydantic model 或 dict）
    """
    spec = get_skill(name)
    if spec is None:
        raise KeyError(f"未注册的技能: {name}，可用: {sorted(SKILL_REGISTRY)}")

    data: dict[str, Any] = dict(payload or {})
    data.update(kwargs)

    model = resolve_input_model(spec)
    if model is None:
        return spec.func(**data)

    validated = model(**data)
    if spec.call_style == "model":
        return spec.func(validated)
    return spec.func(**{k: getattr(validated, k) for k in model.model_fields})


def warm_up() -> Dict[str, str]:
    """
    强制导入全部技能实现模块（仅用于自检/预热），返回 {技能名: "ok"/错误信息}。
    正常启动路径不需要调用——注册表本身是惰性的。
    """
    status: Dict[str, str] = {}
    for name, spec in SKILL_REGISTRY.items():
        try:
            if spec.module:
                importlib.import_module(spec.module)
            status[name] = "ok"
        except Exception as exc:
            status[name] = f"{type(exc).__name__}: {exc}"
            logger.warning("技能预热失败 %s: %s", name, exc)
    return status


__all__ = [
    "SKILL_REGISTRY",
    "SkillSpec",
    "get_skill",
    "list_skills",
    "list_categories",
    "get_openai_tools",
    "invoke_skill",
    "resolve_input_model",
    "warm_up",
    "query_knowledge_pack",
    "list_conflicts",
]
