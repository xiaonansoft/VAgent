# -*- coding: utf-8 -*-
"""
VERO 事件总线 + 约束变化重算触发器（进程内轻量实现）

============================== 红线（写死，不得绕过） ==============================
本模块只生成**建议包**，绝不写入控制回路、绝不下发任何 DCS/PLC 设定值。
写控制参数由 app/core/mode_control.py 的 IControlSignalWriter 负责，
且生产环境**永不使用真实实现**（只允许 Mock 实现），见 mode_control.py 的说明。
=================================================================================

职责
----
1. 定义炉次全链路事件枚举（HEAT_CREATED → ... → ADVICE_CONFIRMED / ADVICE_OVER TURNED）
2. 提供进程内事件总线：subscribe / publish / event_log（带 trace_id、heat_id、时间戳）
3. 提供「约束变化 → 重算」触发器：约束（铁水温度/成分/重量/目标温度等）发生变化时,
   重跑受影响的计算链（SKILL_REGISTRY 中的 calculate_initial_charge + recommend_lance_profile）,
   产出带 requires_human_confirm=True 的**建议包**。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.core.logger import generate_trace_id, get_trace_id, logger

# ============================================================================
# 1. 事件枚举
# ============================================================================


class EventType(str, Enum):
    """炉次全链路事件。注：ADVICE_OVER TURNED 在 Python 中命名为 ADVICE_OVER_TURNED。"""

    HEAT_CREATED = "heat_created"                  # 炉次创建
    CONDITION_ENTERED = "condition_entered"        # 铁水条件/约束录入
    RECIPE_CALCULATED = "recipe_calculated"        # 配料计算完成
    LANCE_RECOMMENDED = "lance_recommended"        # 枪位曲线推荐完成
    ASSAY_ARRIVED = "assay_arrived"                # 化验结果到达（触发复盘/诊断）
    CONSTRAINT_CHANGED = "constraint_changed"      # 约束变化（触发重算）
    ADVICE_CONFIRMED = "advice_confirmed"          # 人工确认采纳建议
    ADVICE_OVER_TURNED = "advice_overturned"       # 人工推翻建议（对应 OverturnRecord）


# ============================================================================
# 2. 事件总线（进程内 / 内存态）
# ============================================================================


@dataclass
class EventRecord:
    """事件日志条目：始终带 trace_id / heat_id / 时间戳，便于回放与审计。"""

    event: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    heat_id: Optional[str] = None
    trace_id: Optional[str] = None
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event.value if isinstance(self.event, EventType) else str(self.event),
            "heat_id": self.heat_id,
            "trace_id": self.trace_id,
            "ts": self.ts.isoformat(),
            "payload": self.payload,
        }


class EventBus:
    """
    极简进程内发布/订阅总线（内存态，不跨进程、不持久化）。

    设计取舍：MVP 阶段不引入 Redis/Kafka；后续如需跨进程，只需替换 publish 的实现，
    订阅方代码不变。
    """

    def __init__(self) -> None:
        self._handlers: Dict[EventType, List[Callable[[EventRecord], Any]]] = {}
        self.event_log: List[EventRecord] = []

    def subscribe(self, event: EventType, handler: Callable[[EventRecord], Any]) -> None:
        """订阅事件。handler 可以是同步函数或协程函数。"""
        self._handlers.setdefault(event, []).append(handler)

    def unsubscribe(self, event: EventType, handler: Callable[[EventRecord], Any]) -> None:
        if handler in self._handlers.get(event, []):
            self._handlers[event].remove(handler)

    def publish(
        self,
        event: EventType,
        payload: Optional[Dict[str, Any]] = None,
        *,
        heat_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> EventRecord:
        """
        发布事件：写 event_log 并同步派发给所有订阅者。

        - 同步 handler：直接调用
        - 异步 handler：已有事件循环则 create_task；否则 asyncio.run 兜底
        - 单个 handler 抛错只记录日志，不影响其他订阅者
        """
        payload = dict(payload or {})
        record = EventRecord(
            event=event,
            payload=payload,
            heat_id=heat_id or payload.get("heat_id"),
            trace_id=trace_id or payload.get("trace_id") or get_trace_id() or generate_trace_id(),
        )
        self.event_log.append(record)

        for handler in list(self._handlers.get(event, [])):
            try:
                result = handler(record)
                if inspect.isawaitable(result):
                    self._schedule(result, handler, record)
            except Exception as exc:  # pragma: no cover - 订阅者隔离
                logger.error(
                    "事件处理失败 event=%s handler=%s: %s",
                    record.event.value,
                    getattr(handler, "__name__", handler),
                    exc,
                    exc_info=True,
                )
        return record

    @staticmethod
    def _schedule(awaitable: Any, handler: Any, record: EventRecord) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(awaitable)
        except RuntimeError:
            asyncio.run(awaitable)

    def clear_log(self) -> None:
        self.event_log.clear()


#: 进程内全局总线
BUS = EventBus()


def subscribe(event: EventType, handler: Callable[[EventRecord], Any]) -> None:
    BUS.subscribe(event, handler)


def publish(
    event: EventType,
    payload: Optional[Dict[str, Any]] = None,
    *,
    heat_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> EventRecord:
    return BUS.publish(event, payload, heat_id=heat_id, trace_id=trace_id)


def event_log(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """返回事件日志（dict 形式，便于序列化）。"""
    records = BUS.event_log if limit is None else BUS.event_log[-limit:]
    return [r.to_dict() for r in records]


# ============================================================================
# 3. 约束变化 → 重算触发器
# ============================================================================

#: 重算所用的默认约束（被 changed_constraints 中的同名键覆盖）
DEFAULT_CONSTRAINTS: Dict[str, Any] = {
    "iron_weight_t": 100.0,
    "iron_temp_c": 1280.0,
    "is_one_can": True,
    "target_temp_c": 1360.0,
    "C": 4.30,
    "Si": 0.22,
    "V": 0.30,
    "Ti": 0.15,
    "P": 0.10,
    "S": 0.05,
}

#: 允许出现在 changed_constraints 中的成分键 → IronInitialAnalysis 字段
_ELEMENT_KEYS = {"C", "Si", "V", "Ti", "P", "S"}
#: Si 的常用别名
_SI_ALIASES = ("Si", "si_content_pct", "si", "Si_pct")


def _normalize_constraints(changed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把外部传入的变更约束规整为统一的内部键（含 Si 别名兼容）。"""
    merged = dict(DEFAULT_CONSTRAINTS)
    for key, value in (changed or {}).items():
        if key in _SI_ALIASES:
            merged["Si"] = float(value)
        elif key in merged or key in _ELEMENT_KEYS:
            merged[key] = value
        else:
            # 未知键也保留，便于溯源，但不参与计算
            merged[key] = value
    return merged


def _knowledge_versions() -> Dict[str, str]:
    """读取当前生效的知识包版本（尽力而为，失败返回空 dict）。"""
    versions: Dict[str, str] = {}
    try:
        import yaml  # 惰性导入

        from app.tools.plant_a_pack import DEFAULT_PLANT, INDUSTRY_PACK

        def _meta(path: str) -> Optional[Dict[str, Any]]:
            with open(path, "r", encoding="utf-8") as f:
                return (yaml.safe_load(f) or {}).get("pack", {})

        industry = _meta(INDUSTRY_PACK)
        if industry:
            versions["industry"] = str(industry.get("version", "unknown"))

        plant = DEFAULT_PLANT
        packs_dir = os.path.dirname(os.path.dirname(INDUSTRY_PACK))
        ppath = os.path.join(packs_dir, plant, "base.yaml")
        pmeta = _meta(ppath)
        if pmeta:
            versions[plant] = str(pmeta.get("version", "unknown"))
    except Exception as exc:
        logger.warning("读取知识包版本失败（不影响重算）: %s", exc)
    return versions


def _skill_versions(names: List[str]) -> Dict[str, str]:
    from app.tools import SKILL_REGISTRY  # 惰性导入（注册表本身也是惰性的）

    return {n: SKILL_REGISTRY[n].version for n in names if n in SKILL_REGISTRY}


def recompute_on_constraint_change(
    heat_id: str,
    changed_constraints: Optional[Dict[str, Any]] = None,
    *,
    trace_id: Optional[str] = None,
    reason: str = "constraint_changed",
) -> Dict[str, Any]:
    """
    约束变化后的重算（同步）。

    重跑受影响的计算链：calculate_initial_charge → recommend_lance_profile，
    产出**建议包**。

    ⚠️ 红线：本函数只返回建议 dict，**不写库、不下发任何 DCS/PLC 设定值**；
       返回的包必须带 requires_human_confirm=True，由人工确认后方可采纳。
    """
    from app.tools import invoke_skill  # 惰性导入（numpy 等只在真正计算时加载）

    tid = trace_id or get_trace_id() or generate_trace_id()
    cons = _normalize_constraints(changed_constraints)

    charge_inputs: Dict[str, Any] = {
        "iron_weight_t": float(cons["iron_weight_t"]),
        "iron_temp_c": float(cons["iron_temp_c"]),
        "iron_analysis": {k: float(cons[k]) for k in _ELEMENT_KEYS},
        "is_one_can": bool(cons["is_one_can"]),
        "target_temp_c": float(cons["target_temp_c"]),
    }

    warnings: List[str] = []
    try:
        charge = invoke_skill("calculate_initial_charge", charge_inputs)
        charge_dump = charge.model_dump() if hasattr(charge, "model_dump") else dict(charge)
    except Exception as exc:
        logger.error("重算失败：配料计算异常 heat_id=%s: %s", heat_id, exc, exc_info=True)
        charge_dump = {"error": f"{type(exc).__name__}: {exc}"}
        warnings.append("配料计算失败，建议包不完整，请勿采纳。")

    si_pct = float(cons["Si"])
    try:
        lance = invoke_skill("recommend_lance_profile", {"si_content_pct": si_pct})
        lance_dump = lance.model_dump() if hasattr(lance, "model_dump") else dict(lance)
        publish(EventType.LANCE_RECOMMENDED, {
            "heat_id": heat_id,
            "si_content_pct": si_pct,
            "mode": lance_dump.get("mode"),
        }, heat_id=heat_id, trace_id=tid)
    except Exception as exc:
        logger.error("重算失败：枪位推荐异常 heat_id=%s: %s", heat_id, exc, exc_info=True)
        lance_dump = {"error": f"{type(exc).__name__}: {exc}"}
        warnings.append("枪位推荐失败，建议包不完整，请勿采纳。")

    publish(EventType.RECIPE_CALCULATED, {
        "heat_id": heat_id,
        "recipe": charge_dump.get("recipe"),
        "oxygen_total_m3": charge_dump.get("oxygen_total_m3"),
    }, heat_id=heat_id, trace_id=tid)

    warnings.extend(charge_dump.get("warnings", []) or [])

    used_skills = ["calculate_initial_charge", "recommend_lance_profile"]

    return {
        "heat_id": heat_id,
        "trace_id": tid,
        "trigger": EventType.CONSTRAINT_CHANGED.value,
        "reason": reason,
        "changed_constraints": dict(changed_constraints or {}),
        "effective_inputs": charge_inputs,
        "advice": {
            "recipe": charge_dump.get("recipe"),
            "oxygen_total_m3": charge_dump.get("oxygen_total_m3"),
            "slag_weight_t": charge_dump.get("slag_weight_t"),
            "v_si_ti_ratio": charge_dump.get("v_si_ti_ratio"),
            "lance_profile": lance_dump,
        },
        "warnings": warnings,
        # ↓↓↓ 红线标记：任何消费方在 requires_human_confirm=True 且未获人工确认前，
        #     不得把 advice 交给控制回路。控制写入只能走 mode_control.IControlSignalWriter
        #     （生产环境永不使用真实实现）。
        "requires_human_confirm": True,
        "control_write": "forbidden",
        "skill_versions": _skill_versions(used_skills),
        "knowledge_versions": _knowledge_versions(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "本建议包仅供人工确认参考，系统不会写入任何 DCS/PLC 控制设定值。",
    }


def on_constraint_changed(record: EventRecord) -> Dict[str, Any]:
    """
    CONSTRAINT_CHANGED 事件的默认处理器：触发重算并返回建议包。

    payload 约定:
        {"heat_id": str, "changed_constraints": {...}, "reason": str（可选）}
    """
    payload = record.payload or {}
    heat_id = payload.get("heat_id") or record.heat_id or "UNKNOWN_HEAT"
    return recompute_on_constraint_change(
        heat_id=heat_id,
        changed_constraints=payload.get("changed_constraints") or {},
        trace_id=record.trace_id,
        reason=payload.get("reason", "constraint_changed"),
    )


def install_default_handlers() -> None:
    """注册默认处理器（幂等）。"""
    if on_constraint_changed not in BUS._handlers.get(EventType.CONSTRAINT_CHANGED, []):
        subscribe(EventType.CONSTRAINT_CHANGED, on_constraint_changed)


install_default_handlers()


__all__ = [
    "EventType",
    "EventRecord",
    "EventBus",
    "BUS",
    "subscribe",
    "publish",
    "event_log",
    "recompute_on_constraint_change",
    "on_constraint_changed",
    "install_default_handlers",
    "DEFAULT_CONSTRAINTS",
]
