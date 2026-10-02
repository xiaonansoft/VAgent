# -*- coding: utf-8 -*-
"""提示词包: 系统提示词 + 知识包冲突注入

VERO 红线: LLM 只做翻译器/检索器/建议器, **零数值计算权**、**不碰控制回路**。
所有提示词模板必须包含 system.py 的三条红线, 不得被下游覆盖。
"""
from __future__ import annotations


from .system import (
    RED_LINES,
    ROLE,
    WORKFLOW,
    STYLE,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_TEMPLATE,
    build_system_prompt,
)
from .conflicts import (
    ConflictRecord,
    KEY_CONFLICT_TOKENS,
    load_known_conflicts,
    render_arbitration_table,
    check_key_conflicts,
    DEFAULT_PACKS_DIR,
)

__all__ = [
    "RED_LINES", "ROLE", "WORKFLOW", "STYLE",
    "SYSTEM_PROMPT", "SYSTEM_PROMPT_TEMPLATE", "build_system_prompt",
    "ConflictRecord", "KEY_CONFLICT_TOKENS", "load_known_conflicts",
    "render_arbitration_table", "check_key_conflicts", "DEFAULT_PACKS_DIR",
]


def build_full_system_prompt(*, packs_dir=None, extra: str | None = None) -> str:
    """一次性组装完整系统提示词: 红线 + 角色 + 口径仲裁表 + 附加约束"""
    table = render_arbitration_table(packs_dir=packs_dir)
    return build_system_prompt(conflicts_table=table, extra=extra)
