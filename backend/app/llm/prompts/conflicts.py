# -*- coding: utf-8 -*-
"""知识包口径冲突 → Prompt 注入 (口径仲裁表)

把 knowledge/packs/{industry,jianlong,pangang}/base.yaml 里的 `known_conflicts`
(CF-001 ~ CF-008) 读取出来, 渲染成一段 Markdown「口径仲裁表」注入系统提示词,
**防止 LLM 在冲突数值上自由发挥** (例如把 Tc 说成 1360/1380, 或把 V/(Si+Ti)
阈值说成 1.01/1.05)。

只读 YAML, 不改 YAML。YAML 加载失败 (缺 pyyaml) 时降级为空表, 不阻断工程。

关键口径 (必须正确渲染):
    CF-007 碳钒转化温度 Tc = 1361℃ (1634K)
    CF-008 V/(Si+Ti) 富集判据阈值 = 1.0
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# backend/app/llm/prompts/conflicts.py → parents[4] = 仓库根
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PACKS_DIR = Path(
    os.getenv("VERO_KNOWLEDGE_PACKS", str(_REPO_ROOT / "knowledge" / "packs"))
)

PACK_ORDER = ["industry", "jianlong", "pangang"]

# 关键冲突: 渲染后必须包含这些值 (用于自检, 防 YAML 结构变化导致静默丢失)
KEY_CONFLICT_TOKENS: Dict[str, List[str]] = {
    "CF-007": ["1361", "1634"],
    "CF-008": ["1.0"],
}


@dataclass
class ConflictRecord:
    id: str
    topic: str
    pack: str
    sources: Dict[str, str] = field(default_factory=dict)
    arbitration: str = ""
    resolved_by: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def sources_text(self) -> str:
        if not self.sources:
            return "-"
        return "<br>".join(f"{k}: {v}" for k, v in self.sources.items())


def _load_yaml(path: Path) -> Dict[str, Any]:
    import yaml  # 延迟导入: 缺 pyyaml 时由调用方降级
    # 厂级知识包属保密资产, 允许不随仓库分发; 缺失时降级为空集。
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _to_record(item: Dict[str, Any], pack: str) -> Optional[ConflictRecord]:
    if not isinstance(item, dict) or not item.get("id"):
        return None
    # pangang 包为扁平结构: 除元字段外均为来源口径
    skip = {"id", "topic", "arbitration", "resolved_by", "note"}
    src = item.get("sources")
    return ConflictRecord(
        id=str(item.get("id")),
        topic=str(item.get("topic", "")),
        pack=pack,
        # pangang 包为扁平结构: 除元字段外均为来源口径; industry/jianlong 为 sources 嵌套
        sources=({str(k): str(v) for k, v in src.items()} if isinstance(src, dict)
                 else {str(k): str(v) for k, v in item.items() if k not in skip}),
        # 无显式仲裁时退到 note (如 CF-005「建议并存」)
        arbitration=str(item.get("arbitration") or item.get("note") or ""),
        resolved_by=str(item.get("resolved_by", "") or ""),
        raw=item,
    )


def load_known_conflicts(packs_dir: Optional[Path] = None) -> List[ConflictRecord]:
    """按 industry → jianlong → pangang 顺序加载 known_conflicts。

    加载失败 (目录缺失 / 缺 pyyaml) 返回空列表, 不抛异常。
    """
    base = Path(packs_dir) if packs_dir else DEFAULT_PACKS_DIR
    out: List[ConflictRecord] = []
    for pack in PACK_ORDER:
        path = base / pack / "base.yaml"
        if not path.is_file():
            continue
        try:
            data = _load_yaml(path)
        except Exception:
            continue
        for item in (data.get("known_conflicts") or []):
            rec = _to_record(item, pack)
            if rec:
                out.append(rec)
    out.sort(key=lambda r: r.id)
    return out


def render_arbitration_table(
    conflicts: Optional[List[ConflictRecord]] = None,
    *,
    packs_dir: Optional[Path] = None,
) -> str:
    """渲染 Markdown「口径仲裁表」(无冲突时返回空串)。"""
    records = conflicts if conflicts is not None else load_known_conflicts(packs_dir)
    if not records:
        return ""

    lines = [
        "| 编号 | 话题 | 冲突来源 | 仲裁结论(必须采用) | 定案 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in records:
        resolved = r.arbitration or "-"
        if r.resolved_by:
            resolved += f" (定案: {r.resolved_by})"
        lines.append(
            f"| {r.id} | {r.topic} | {r.sources_text()} | {resolved} | {r.pack} |"
        )
    return "\n".join(lines)


def check_key_conflicts(table: str) -> Dict[str, bool]:
    """自检: 关键冲突的关键数值是否真的渲染出来了 (防静默丢失)"""
    return {
        cid: all(tok in table for tok in toks)
        for cid, toks in KEY_CONFLICT_TOKENS.items()
    }
