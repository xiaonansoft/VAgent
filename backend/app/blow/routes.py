# -*- coding: utf-8 -*-
"""VERO 吹炼会话路由 —— 冶炼中实时推理 API（SSE + 建议决策 + 复盘报告）

全部只读/建议语义：无任何控制写入端点（scripts/security_scan.py 断言）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .session import RULE_VERSION, BlowManager
from ..tools import list_conflicts, query_knowledge_pack
from ..tools.plant_a_reference import PlantAInputs, MetalAnalysis, run_plant_a_model
from ..tools.initial_charge import calculate_initial_charge
from ..schemas import InitialChargeInputs, IronInitialAnalysis


class BlowStartRequest(BaseModel):
    """开吹请求：铁水化验条件（同 /api/plant_a/charge 口径）+ 演示参数。"""
    C: float = 4.3
    Si: float = 0.19
    V: float = 0.319
    Ti: float | None = None
    iron_weight_kg: float = 80000.0
    iron_temp_c: float = 1290.0
    o2_flow_nm3_h: float = 12000.0
    scenario: str = Field(default="normal", description="normal | hot_metal | high_si")
    time_scale: float = Field(default=10.0, description="演示时间倍速（1=实时，10=10倍速）")
    total_min: float = 10.0


class DecisionRequest(BaseModel):
    advice_id: str
    decision: str = Field(..., description="adopt | reject")
    user: str = "operator"


class PlantBChargeRequest(BaseModel):
    """B 厂查表配料请求（M18：同一引擎、双厂知识包）。"""
    C: float = 4.2
    Si: float = 0.19
    V: float = 0.28
    Ti: float = 0.10
    P: float = 0.08
    S: float = 0.03
    Mn: float = 0.20
    iron_weight_t: float = 80.0
    iron_temp_c: float = 1300.0
    is_one_can: bool = True
    target_temp_c: float = 1360.0


class ChargeSheetRequest(BaseModel):
    """开吹指令单（F1.7）：方案 + 签字 → 留痕（确认即留痕，非执行）。"""
    plant: str = "plant_a"
    C: float
    Si: float
    V: float
    iron_temp_c: float
    iron_weight_kg: float
    recipe_kg: dict
    pred_grade: float | None = None
    add_order: list[str] = Field(default_factory=list, description="加料顺序（块状先于散状等）")
    confirmed_by: str = "二助手"
    reviewed_by: str | None = Field(default=None, description="炉长签字位")


def build_blow_router(manager: BlowManager) -> APIRouter:
    router = APIRouter()

    def _run_plan(req: BlowStartRequest) -> Dict[str, Any]:
        """调用四大平衡引擎生成开吹方案（与前段 /api/plant_a/charge 同口径）。"""
        base = PlantAInputs()
        base.iron_weight = req.iron_weight_kg
        d = base.iron
        base.iron = MetalAnalysis(
            C=req.C, Si=req.Si, V=req.V,
            Mn=req.Mn if hasattr(req, "Mn") else d.Mn,
            P=d.P, S=d.S, Cr=d.Cr,
            Ti=req.Ti if req.Ti is not None else d.Ti,
            temp=req.iron_temp_c)
        r = run_plant_a_model(base)
        recipe = {k: (round(v, 1) if v else 0.0) for k, v in r.after["coolant_weights"].items()}
        # 加料路径映射：球团/铁皮=散状（称量斗可事中补）；生铁/块矿=块状（天车，开吹前一次配足）
        scatter = recipe.get("pellet", 0.0) + recipe.get("iron_scale", 0.0)
        block = recipe.get("metal_fe", 0.0) + recipe.get("ore", 0.0)
        return {"recipe_kg": recipe, "scatter_kg": scatter, "block_kg": block,
                "pred_grade": round(r.v2o5_grade, 2),
                "slag_total": round(r.after["slag"], 0),
                "heat_surplus_mj": round(r.heat["surplus"] / 1e6, 1)}

    @router.post("/blow/start")
    async def blow_start(req: BlowStartRequest):
        if req.scenario not in ("normal", "hot_metal", "high_si"):
            raise HTTPException(400, "scenario 须为 normal/hot_metal/high_si")
        plan = _run_plan(req)
        sess = manager.create(
            C=req.C, Si=req.Si, V=req.V, Ti=req.Ti if req.Ti is not None else 0.15,
            temp_c=req.iron_temp_c, weight_kg=req.iron_weight_kg,
            o2_flow_nm3_h=req.o2_flow_nm3_h, scenario=req.scenario,
            time_scale=req.time_scale, total_min=req.total_min,
            scatter_kg=plan["scatter_kg"], block_kg=plan["block_kg"],
            pred_grade_plan=plan["pred_grade"])
        sess.start()
        return {"session_id": sess.id, "plan": plan,
                "time_scale": sess.time_scale, "total_min": req.total_min,
                "note": "真值炉按场景施加扰动，对界面不可见；估计与建议只基于化验单+观测"}

    @router.get("/blow/sessions")
    async def blow_sessions():
        out = []
        for s in sorted(manager.sessions.values(), key=lambda x: x.created, reverse=True):
            snap = s.snapshot()
            out.append({"session_id": s.id, "t_min": snap["t_min"], "finished": s.finished,
                        "scenario": s.scenario, "advices": len(s.advices),
                        "est_T": snap["est"]["T"], "est_V": snap["est"]["V"],
                        "tc_margin_c": snap["tc_margin_c"], "tc_alarm": snap["tc_alarm"],
                        "alarms": len(snap["alarms"]), "progress": snap["progress"],
                        "pred_T": (s.pred or {}).get("T"),
                        "phase": snap["sop"]["name"] if snap.get("sop") else "",
                        "stop_reason": s.stop_reason})
        return out

    @router.get("/blow/{sid}/stream")
    async def blow_stream(sid: str, req: Request):
        sess = manager.get(sid)
        if sess is None:
            raise HTTPException(404, f"会话不存在: {sid}")

        async def gen():
            final_pushes = 0
            while not await req.is_disconnected():
                snap = sess.snapshot()
                yield {"data": json.dumps(snap, ensure_ascii=False)}
                if sess.finished:
                    final_pushes += 1
                    if final_pushes >= 3:
                        break
                await asyncio.sleep(1.0)

        return EventSourceResponse(gen())

    @router.post("/blow/{sid}/decision")
    async def blow_decision(sid: str, body: DecisionRequest):
        sess = manager.get(sid)
        if sess is None:
            raise HTTPException(404, f"会话不存在: {sid}")
        if body.decision not in ("adopt", "reject"):
            raise HTTPException(400, "decision 须为 adopt/reject")
        r = sess.decide(body.advice_id, body.decision, body.user)
        if not r.get("ok"):
            raise HTTPException(409, r.get("error", "决策失败"))
        return r

    @router.post("/blow/{sid}/stop")
    async def blow_stop(sid: str, user: str = "operator"):
        sess = manager.get(sid)
        if sess is None:
            raise HTTPException(404, f"会话不存在: {sid}")
        sess.finish(f"manual_stop_by_{user}")
        return {"ok": True, "session_id": sid, "note": "提枪为人工动作——系统仅记录终点时刻"}

    @router.get("/blow/{sid}/report")
    async def blow_report(sid: str):
        sess = manager.get(sid)
        if sess is None:
            raise HTTPException(404, f"会话不存在: {sid}")
        return sess.report()

    # --- 开吹指令单（内存留痕，演示口径） ---
    _charge_sheets: dict = {}

    @router.post("/blow/charge-sheet")
    async def create_charge_sheet(body: ChargeSheetRequest):
        import uuid as _uuid
        from datetime import datetime as _dt
        sid = "CS-" + _uuid.uuid4().hex[:8]
        sheet = {
            "sheet_id": sid,
            "created_at": _dt.utcnow().isoformat() + "Z",
            "rule_version": RULE_VERSION,
            **body.model_dump(),
            "confirmed": True,
        }
        _charge_sheets[sid] = sheet
        return sheet

    @router.get("/blow/charge-sheet/latest")
    async def latest_charge_sheet():
        if not _charge_sheets:
            return {}
        return sorted(_charge_sheets.values(), key=lambda s: s["created_at"])[-1]

    # --- B 厂查表配料（M18 双厂对照） ---
    @router.post("/plant_b/charge")
    async def plant_b_charge(req: PlantBChargeRequest):
        inp = InitialChargeInputs(
            iron_weight_t=req.iron_weight_t, iron_temp_c=req.iron_temp_c,
            iron_analysis=IronInitialAnalysis(C=req.C, Si=req.Si, V=req.V, Ti=req.Ti,
                                              P=req.P, S=req.S, Mn=req.Mn),
            is_one_can=req.is_one_can, target_temp_c=req.target_temp_c)
        r = calculate_initial_charge(inp)
        return {
            "engine": "plant_b 查表法（规程口径 · knowledge/packs/plant_b）",
            "rule_version": "plant_b lookup v1.0.0 (108 组等价对照零漂移)",
            "recipe_t": {k: round(v, 3) for k, v in r.recipe.items()},
            "oxygen_total_m3": round(r.oxygen_total_m3, 0),
            "slag_weight_t": round(r.slag_weight_t, 3),
            "v_si_ti_ratio": round(r.v_si_ti_ratio, 4),
            "warnings": r.warnings,
        }

    @router.get("/knowledge/conflicts")
    async def knowledge_conflicts():
        """三层聚合冲突清单（industry + plant_a + 厂级；缺失显式降级）。"""
        return list_conflicts()

    @router.get("/knowledge/param")
    async def knowledge_param(path: str = "", plant: str | None = None):
        return query_knowledge_pack(param_path=path, plant=plant)

    return router
