# -*- coding: utf-8 -*-
"""VERO LLM 网关 (LLM Gateway) —— 对话层的工程化底座

VERO 红线 (本包所有模块强制遵守)
--------------------------------
LLM 在 VERO 中只做 **翻译器 / 检索器 / 建议器**：

* **零数值计算权** —— LLM 不得自行计算、估算、插值、外推任何物理量
  (品位/温度/氧量/渣量/收得率...)。所有数值必须来自确定性引擎的 tool_call 返回,
  并经 `validators.verify_numbers` 溯源校验。
* **不碰控制回路** —— LLM 不得下发氧枪枪位、供氧流量、吹炼时长等控制设定值,
  只输出建议文本, 由人工或既有控制逻辑决定是否采纳。

`client.py` 负责与 DeepSeek/OpenAI 兼容端点通信, 并在无 API Key 时自动降级为
`dry_run`(结构化占位), 保证工程可**完全离线运行**。

离线运行验证:
    cd /Users/yanwenqing/Documents/VAgent
    PYTHONPATH=backend python -m app.llm        # 或 python -c "import app.llm; app.llm.self_check()"
"""

from __future__ import annotations

from .client import (
    LLMDisabled,
    LLMError,
    LLMClient,
    LLMConfig,
    ChatMessage,
    ChatResponse,
    UsageMeter,
    get_client,
    is_enabled,
)
from .router import (
    RouteResult,
    route,
    tool_schemas,
    tool_schema_source,
    fallback_tool_schemas,
)
from .validators import (
    UnverifiableNumberError,
    extract_numbers,
    verify_numbers,
    validate_with_model,
)
from .prompts import (
    SYSTEM_PROMPT,
    build_system_prompt,
    build_full_system_prompt,
    RED_LINES,
)
from .prompts.conflicts import (
    ConflictRecord,
    load_known_conflicts,
    render_arbitration_table,
    check_key_conflicts,
)

__all__ = [
    # client
    "LLMDisabled", "LLMError", "LLMClient", "LLMConfig",
    "ChatMessage", "ChatResponse", "UsageMeter", "get_client", "is_enabled",
    # router
    "RouteResult", "route", "tool_schemas", "tool_schema_source", "fallback_tool_schemas",
    # validators
    "UnverifiableNumberError", "extract_numbers", "verify_numbers", "validate_with_model",
    # prompts
    "SYSTEM_PROMPT", "build_system_prompt", "build_full_system_prompt", "RED_LINES",
    "ConflictRecord", "load_known_conflicts", "render_arbitration_table",
    "check_key_conflicts",
]

__version__ = "0.1.0-skeleton"


def self_check() -> dict:
    """离线自检: 不联网、不消耗 token, 返回骨架各部件的可用状态。

    用于 CI/本地快速确认 LLM 网关可离线跑通。
    """
    client = get_client()
    probe = client.chat([
        ChatMessage(role="user", content="这炉钒渣品位多少?"),
    ])
    routed = route("帮我算一下这炉的开吹配料和氧量")
    conflicts = load_known_conflicts()
    table = render_arbitration_table(conflicts)
    try:
        verify_numbers("品位 13.29%，收得率 91.2%", [{"grade": 14.5}])
        verify_ok = False          # 无溯源数值本应被拦截, 走到这里说明校验失效
    except UnverifiableNumberError:
        verify_ok = True

    return {
        "llm_enabled": client.enabled,
        "dry_run": bool(getattr(probe, "dry_run", False)),
        "probe_answer": probe.content[:120],
        "route_intent": routed.intent,
        "route_tool": routed.tool_name,
        "tool_schema_count": len(tool_schemas()),
        "tool_schema_source": tool_schema_source(),
        "conflict_count": len(conflicts),
        "conflict_ids": [c.id for c in conflicts],
        "key_conflicts_rendered": check_key_conflicts(table),
        "numbers_intercepted": verify_ok,
        "usage": client.usage.snapshot(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(self_check(), ensure_ascii=False, indent=2))
