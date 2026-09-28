# -*- coding: utf-8 -*-
"""意图路由骨架 (user_text → {intent, tool_name, arguments})

VERO 红线: LLM 只做翻译器/检索器/建议器, **零数值计算权**、**不碰控制回路**。
路由的职责只有一件事: 把自然语言**指向**确定性引擎工具, 参数由工具自己校验与计算;
路由层不产生、不推导任何数值。

工具 schema **复用** backend/app/mcp/tools_server.py 的 `_tool_schemas()`,
不另起炉灶; 若该模块因缺少 fastapi/mcp 依赖而导入失败, 回退到
`FALLBACK_TOOL_SCHEMAS` 静态清单 (与 MCP 侧保持同名同义, 仅为降级用)。

TODO(P1 接入 LLM): 当前为关键词规则兜底。接真 Key 后用 LLM function calling
替换 `_rule_route`, 接口签名 `route(user_text) -> RouteResult` 保持不变;
替换后仍须经 `app.llm.validators.verify_numbers` 做数值溯源校验。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .client import LLMClient, get_client

# ---------------------------------------------------------------------------
# 工具 schema: 复用 MCP, 失败回退
# ---------------------------------------------------------------------------

# 降级用静态工具清单 (仅当 app.mcp.tools_server 不可导入时使用)
FALLBACK_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "calculate_initial_charge": {
        "description": "L1 静态配料模型: 计算开吹配料与氧量 (SDM)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "simulate_blow_path": {
        "description": "L2 动态仿真模型: 提钒动力学微分方程推演",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "diagnose_process_quality": {
        "description": "炉后过程诊断: 钒渣品位与收得率评估",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "calculate_thermal_balance": {
        "description": "热平衡与冷料推荐 (简版)",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "recommend_lance_profile": {
        "description": "供氧枪位策略建议 (只给建议, 不下发控制设定值)",
        "inputSchema": {"type": "object", "properties": {"si_content_pct": {"type": "number"}},
                       "required": ["si_content_pct"]},
    },
    "predict_critical_temp": {
        "description": "临界温度与裕度预测 (Tc)",
        "inputSchema": {"type": "object", "properties": {}},
    },
}


def tool_schemas() -> Dict[str, Dict[str, Any]]:
    """工具 schema 单一来源: 优先 MCP `_tool_schemas()`, 导入失败则回退静态清单"""
    try:
        from ..mcp.tools_server import _tool_schemas  # noqa: WPS433 (延迟导入: 依赖可能缺失)
        schemas = _tool_schemas()
        if schemas:
            return schemas
    except Exception:
        pass
    return dict(FALLBACK_TOOL_SCHEMAS)


def tool_schema_source() -> str:
    """当前工具 schema 的实际来源: 'mcp' (复用 MCP 权威) 或 'fallback' (降级静态清单)"""
    try:
        from ..mcp.tools_server import _tool_schemas  # noqa: WPS433
        return "mcp" if _tool_schemas() else "fallback"
    except Exception:
        return "fallback"


def fallback_tool_schemas() -> Dict[str, Dict[str, Any]]:
    return dict(FALLBACK_TOOL_SCHEMAS)


def tools_as_openai_tools() -> List[Dict[str, Any]]:
    """转为 OpenAI/DeepSeek function calling 的 tools 数组"""
    return [
        {"type": "function",
         "function": {"name": name,
                      "description": meta.get("description", ""),
                      "parameters": meta.get("inputSchema", {"type": "object", "properties": {}})}}
        for name, meta in tool_schemas().items()
    ]


# ---------------------------------------------------------------------------
# 路由结果
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    intent: str                        # 意图枚举, 见 INTENTS
    tool_name: Optional[str] = None    # 目标确定性工具 (None=无需工具, 纯检索/闲聊)
    arguments: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    method: str = "rule"               # rule | llm_function_call
    missing: List[str] = field(default_factory=list)   # 缺失必填参数名
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"intent": self.intent, "tool_name": self.tool_name,
                "arguments": self.arguments, "confidence": self.confidence,
                "method": self.method, "missing": self.missing, "note": self.note}


INTENTS = {
    "charge":    "L1 开吹配料/氧量计算",
    "simulate":  "L2 吹炼过程动力学仿真",
    "diagnose":  "炉后过程诊断(品位/收得率归因)",
    "thermal":   "热平衡与冷料配吃",
    "lance":     "氧枪枪位策略建议",
    "critical":  "碳钒转化临界温度 Tc 查询",
    "explain":   "术语/知识检索(纯解释, 不产生数值)",
    "unknown":   "未识别",
}

# 关键词 → (intent, tool_name)
KEYWORDS: List[tuple[str, str, str]] = [
    (r"配料|装料|入炉|加多少|冷料|废钢|生铁块|氧耗|氧量|开吹", "charge", "calculate_initial_charge"),
    (r"仿真|模拟|推演|吹炼路径|动力学|过程曲线|吹炼过程", "simulate", "simulate_blow_path"),
    (r"诊断|归因|为什么|偏低|不达标|收得率|品位低|分析.*炉次", "diagnose", "diagnose_process_quality"),
    (r"热平衡|热量|富余|配吃|冷却剂|温度.*平衡", "thermal", "calculate_thermal_balance"),
    (r"枪位|氧枪|低-高-低|压枪|供氧策略", "lance", "recommend_lance_profile"),
    (r"临界温度|转化温度|Tc|碳钒转化|保碳.*温度", "critical", "predict_critical_temp"),
    (r"是什么|什么意思|术语|解释|怎么理解|口径|区别", "explain", None),
]

# 从文本中抓取的参数名 → 正则 (供规则兜底填参; 真正的参数校验由工具侧 pydantic 完成)
ARG_PATTERNS: Dict[str, str] = {
    "si_content_pct": r"(?:si|硅)[^\d\-]{0,6}(\d+(?:\.\d+)?)\s*%?",
    "v_content_pct":  r"(?:v|钒)[^\d\-]{0,6}(\d+(?:\.\d+)?)\s*%?",
    "current_temp_c": r"(\d{3,4}(?:\.\d+)?)\s*(?:℃|度|C\b)",
    "iron_weight_kg": r"(\d+(?:\.\d+)?)\s*(?:t|吨|kg)",
}


def _extract_args(text: str) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    low = text.lower()
    for key, pat in ARG_PATTERNS.items():
        m = re.search(pat, low, re.I)
        if m:
            try:
                args[key] = float(m.group(1))
            except ValueError:
                pass
    return args


def _rule_route(text: str) -> RouteResult:
    for pat, intent, tool in KEYWORDS:
        if re.search(pat, text, re.I):
            args = _extract_args(text)
            missing: List[str] = []
            if tool:
                schema = tool_schemas().get(tool, {})
                required = (schema.get("inputSchema") or {}).get("required", []) or []
                missing = [r for r in required if r not in args]
            return RouteResult(
                intent=intent, tool_name=tool, arguments=args,
                confidence=0.6 if not missing else 0.35,
                method="rule", missing=missing,
                note="关键词规则兜底; 接 LLM function calling 后由模型填参",
            )
    return RouteResult(intent="unknown", tool_name=None, confidence=0.0, method="rule",
                       note="未命中任何意图; TODO: 交 LLM 判定或向用户澄清")


def route(user_text: str, *, client: Optional[LLMClient] = None) -> RouteResult:
    """意图路由主入口。

    当前为规则兜底 (离线可用)。`client` 传入且 LLM 已启用时,
    仍走规则 —— function calling 接入见下方 TODO。
    """
    text = (user_text or "").strip()
    if not text:
        return RouteResult(intent="unknown", tool_name=None, note="空输入")

    # TODO(P1): 接 LLM function calling —— 伪代码:
    #   cli = client or get_client()
    #   if cli.enabled:
    #       resp = cli.chat([ChatMessage(role="system", content=SYSTEM_PROMPT),
    #                        ChatMessage(role="user", content=text)],
    #                       tools=tools_as_openai_tools())
    #       if resp.tool_calls:
    #           fn = resp.tool_calls[0]["function"]
    #           return RouteResult(intent=_intent_of(fn["name"]),
    #                              tool_name=fn["name"],
    #                              arguments=json.loads(fn["arguments"] or "{}"),
    #                              confidence=0.9, method="llm_function_call")
    #   注意: 即使走 LLM, 参数数值也必须能被 validators 溯源或被用户原文佐证。
    return _rule_route(text)
