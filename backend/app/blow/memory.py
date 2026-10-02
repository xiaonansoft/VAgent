# -*- coding: utf-8 -*-
"""VERO 智能体跨炉记忆（agent memory）

反思回路：收炉 Reviewer 把本炉教训/模式写入记忆；下炉开炉时检索同场景记忆，
显式引用（播报"引用上炉经验#N"），只用于估计先验与监控阈值——绝不自动写 k 常数。
存储：knowledge/data/private/agent_memory.json（gitignored，离线单机）。
条目自带 source/confidence，可整库删除（可关）。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List

_REPO = os.path.join(os.path.dirname(__file__), "..", "..", "..")
MEM_PATH = os.environ.get(
    "VERO_AGENT_MEMORY",
    os.path.join(_REPO, "knowledge", "data", "private", "agent_memory.json"))
_LOCK = threading.Lock()


def load_memories(scenario: str | None = None, limit: int = 8) -> List[Dict[str, Any]]:
    """读取记忆（可按场景过滤），最近的在前。"""
    try:
        with _LOCK:
            with open(MEM_PATH, "r", encoding="utf-8") as f:
                items = json.load(f)
    except Exception:
        return []
    if scenario:
        items = [m for m in items if m.get("scenario") in (scenario, "any")]
    return items[-limit:][::-1]


def save_memories(entries: List[Dict[str, Any]]) -> int:
    """追加写入（带去重键），返回本次新增条数。"""
    os.makedirs(os.path.dirname(MEM_PATH), exist_ok=True)
    with _LOCK:
        try:
            with open(MEM_PATH, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
        known = {(m.get("kind"), m.get("content")) for m in items}
        added = 0
        for e in entries:
            key = (e.get("kind"), e.get("content"))
            if key in known:
                continue
            e["id"] = len(items) + 1
            items.append(e)
            known.add(key)
            added += 1
        with open(MEM_PATH, "w", encoding="utf-8") as f:
            json.dump(items[-200:], f, ensure_ascii=False, indent=1)
        return added


def build_review_entries(scenario: str, heat_id: str, *, ir_bias_c: float,
                         coverage_t: float, adopted_kg: float,
                         tc_crossed: bool, final_v: float) -> List[Dict[str, Any]]:
    """收炉 Reviewer：把本炉对账结论转成结构化经验（只在有据时产出）。"""
    out = [{"heat_id": heat_id, "scenario": scenario, "kind": "模式",
            "content": f"{scenario} 场景收炉：余钒 {final_v:.3f}%，"
                       f"{'曾越 Tc，下炉同场景应更早进入补冷预判' if tc_crossed else '未越线，节奏可用'}",
            "confidence": 0.6, "source": "reviewer"}]
    if abs(ir_bias_c) >= 4.0:
        out.append({"heat_id": heat_id, "scenario": scenario, "kind": "教训",
                    "content": f"红外软测量偏置约 {ir_bias_c:+.0f}℃（估计-真值漂移），下炉同场景估计先验应{('上调' if ir_bias_c>0 else '下调')}这量级",
                    "confidence": 0.7, "source": "reviewer"})
    if coverage_t is not None and coverage_t < 0.6:
        out.append({"heat_id": heat_id, "scenario": scenario, "kind": "教训",
                    "content": f"σ 带覆盖率仅 {coverage_t*100:.0f}%——误差带过窄，下炉同场景应放宽 σ 增长",
                    "confidence": 0.6, "source": "reviewer"})
    if adopted_kg > 0:
        out.append({"heat_id": heat_id, "scenario": scenario, "kind": "模式",
                    "content": f"采纳补冷 {adopted_kg:.0f}kg 后温度回落符合预期——该量级的干预记录在案",
                    "confidence": 0.6, "source": "reviewer"})
    return out
