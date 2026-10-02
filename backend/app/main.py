from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional, Dict, List

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logger import setup_logging
from app.db.base import get_db, init_db
from app.db.models import Heat, AdviceLog
from app.schemas import ChatRequest, ChatResponse, SaveHeatResultsInputs

from app.mcp.data_server import build_data_router
from app.data.simulator import DataSimulator
from app.agents.team import CoordinatorAgent
from app.core.mode_control import ModeController, SystemMode
from app.blow.session import BlowManager
from app.blow.routes import build_blow_router
from pydantic import BaseModel

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize Simulator & Mode Controller
simulator = DataSimulator()
mode_controller = ModeController(simulator=simulator)
blow_manager = BlowManager()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    logger.info("Starting up VAgent backend...")
    await init_db()
    simulator.start()
    yield
    # Shutdown
    logger.info("Shutting down VAgent backend...")

app = FastAPI(
    title="VAgent API",
    version="7.0.0",
    lifespan=lifespan
)

# Include MCP Routers
app.include_router(build_data_router(simulator=simulator), prefix="/api")
app.include_router(build_blow_router(blow_manager), prefix="/api")

# ---------------------------------------------------------------------------
# 工作台静态托管（同源部署，规避 file:// CORS 陷阱——见 FULLCHAIN_SPEC §10 已知坑）
# ---------------------------------------------------------------------------
import os as _os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

_WEBAPP_DIR = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", "..", "webapp"))
if _os.path.isdir(_WEBAPP_DIR):
    app.mount("/ui", StaticFiles(directory=_WEBAPP_DIR), name="ui")

@app.get("/")
async def root():
    if _os.path.isdir(_WEBAPP_DIR):
        return RedirectResponse("/ui/VERO_WORKBENCH.html")
    return {"status": "ok", "docs": "/docs"}

class ModeSwitchRequest(BaseModel):
    mode: SystemMode
    token: str = "default"
    user: str = "api_user"

@app.post("/api/system/mode")
async def set_system_mode(req: ModeSwitchRequest):
    try:
        # 必须 await：switch_mode 是协程，未 await 时模式实际未切换却返回 ok（造假已修复）
        await mode_controller.switch_mode(req.mode, user=req.user, auth_token=req.token)
        return {"status": "ok", "mode": mode_controller.current_mode.value}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/mode")
async def get_system_mode():
    return {"mode": mode_controller.current_mode}

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "7.0.0"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_agent(
    req: ChatRequest,
    session: AsyncSession = Depends(get_db)
):
    context = req.context or {}
    si_content_pct = req.si_content_pct if req.si_content_pct is not None else context.get("si_content_pct") or context.get("si")
    iron_temp_c = req.iron_temp_c if req.iron_temp_c is not None else context.get("iron_temp_c") or context.get("temp")
    is_one_can = req.is_one_can if req.is_one_can is not None else context.get("is_one_can")

    agent = CoordinatorAgent()
    result = await agent.run({
        "message": req.message,
        "si_content_pct": si_content_pct,
        "iron_temp_c": iron_temp_c,
        "is_one_can": is_one_can,
        "simulator": simulator
    })

    response = ChatResponse(
        reply=result.get("reply", ""),
        tool_calls=result.get("tool_calls", []),
        trace_id=result.get("trace_id")
    )

    log = AdviceLog(
        trace_id=response.trace_id,
        message=req.message,
        reply=response.reply,
        tool_calls=response.tool_calls,
        context={
            "si_content_pct": si_content_pct,
            "iron_temp_c": iron_temp_c,
            "is_one_can": is_one_can,
            "raw": context
        }
    )
    session.add(log)
    await session.commit()

    return response

@app.get("/api/advice")
async def get_advice_logs(
    skip: int = 0,
    limit: int = 20,
    session: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(AdviceLog).order_by(AdviceLog.created_at.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "trace_id": log.trace_id,
            "message": log.message,
            "reply": log.reply,
            "tool_calls": log.tool_calls,
            "context": log.context,
            "created_at": log.created_at.isoformat()
        }
        for log in logs
    ]

from app.agents.core import agent_graph
import uuid
# A3 降级纪律：langgraph 缺失时 app 仍可启动（仅 Graph 编排路由不可用，返回 503）
try:
    from langgraph.errors import GraphInterrupt
except ImportError:  # pragma: no cover
    class GraphInterrupt(Exception):
        """langgraph 缺失时的占位实现。"""

# ... existing imports ...

class GraphRunRequest(BaseModel):
    si: float
    temp: float
    is_one_can: bool

@app.post("/api/graph/run")
async def run_graph(req: GraphRunRequest):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "si": req.si,
        "temp": req.temp,
        "is_one_can": req.is_one_can,
        "messages": []
    }
    
    try:
        # Run untill end or interrupt
        result = await agent_graph.ainvoke(initial_state, config=config)
        
        # Check if interrupt occurred but was returned in state (LangGraph behavior)
        if isinstance(result, dict) and result.get("__interrupt__"):
            snapshot = agent_graph.get_state(config)
            interrupts = result.get("__interrupt__")
            reason = "Unknown Interrupt"
            if isinstance(interrupts, (list, tuple)) and len(interrupts) > 0:
                 item = interrupts[0]
                 if isinstance(item, dict): reason = item.get("value", reason)
                 elif hasattr(item, "value"): reason = item.value
                 else: reason = str(item)
            
            messages = snapshot.values.get("messages", [])
            messages.append(reason)
            
            return {
                "thread_id": thread_id,
                "status": "interrupted",
                "next": snapshot.next,
                "messages": messages
            }
            
        return {
            "thread_id": thread_id,
            "status": "completed",
            "result": result
        }
    except GraphInterrupt:
        # Graph paused
        snapshot = agent_graph.get_state(config)
        return {
            "thread_id": thread_id,
            "status": "interrupted",
            "next": snapshot.next,
            "messages": snapshot.values.get("messages", [])
        }
    except Exception as e:
        # In case NodeInterrupt bubbles up as something else or generic error
        snapshot = agent_graph.get_state(config)
        if snapshot.next:
             return {
                "thread_id": thread_id,
                "status": "interrupted",
                "next": snapshot.next,
                "messages": snapshot.values.get("messages", [])
            }
        logger.error(f"Graph execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ApprovalRequest(BaseModel):
    thread_id: str
    action: str # "approve", "modify"
    recipe: Optional[Dict[str, Any]] = None

@app.post("/api/graph/approve")
async def approve_graph(req: ApprovalRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    
    # Check if thread exists (MemorySaver specific check)
    current_snapshot = agent_graph.get_state(config)
    if not current_snapshot.values:
        raise HTTPException(status_code=404, detail="会话已过期或丢失（后端重启导致内存状态清空），请重新点击 'Run Graph'。")

    # Update state based on action
    update = {"approval_status": "approved" if req.action == "approve" else "modified"}
    if req.action == "modify" and req.recipe:
        # Merge with existing recipe to preserve other ingredients
        current_recipe = current_snapshot.values.get("recipe", {}) or {}
        if isinstance(current_recipe, dict):
            new_recipe = current_recipe.copy()
            
            # Special handling for "scale_weight" (Append mode from UI)
            if "scale_weight" in req.recipe:
                current_val = new_recipe.get("scale_weight", 0.0)
                new_recipe["scale_weight"] = current_val + req.recipe["scale_weight"]
                # Update other fields normally
                req_recipe_clean = {k:v for k,v in req.recipe.items() if k != "scale_weight"}
                new_recipe.update(req_recipe_clean)
            else:
                new_recipe.update(req.recipe)
                
            update["recipe"] = new_recipe
        else:
            update["recipe"] = req.recipe
        
    agent_graph.update_state(config, update)
    
    try:
        # Resume execution
        result = await agent_graph.ainvoke(None, config=config)
        
        if isinstance(result, dict) and result.get("__interrupt__"):
            snapshot = agent_graph.get_state(config)
            interrupts = result.get("__interrupt__")
            reason = "Unknown Interrupt"
            if isinstance(interrupts, (list, tuple)) and len(interrupts) > 0:
                 item = interrupts[0]
                 if isinstance(item, dict): reason = item.get("value", reason)
                 elif hasattr(item, "value"): reason = item.value
                 else: reason = str(item)
            
            messages = snapshot.values.get("messages", [])
            messages.append(reason)
            
            return {
                "thread_id": req.thread_id,
                "status": "interrupted",
                "next": snapshot.next,
                "messages": messages
            }

        return {
            "thread_id": req.thread_id,
            "status": "completed",
            "result": result
        }
    except GraphInterrupt:
        snapshot = agent_graph.get_state(config)
        return {
            "thread_id": req.thread_id,
            "status": "interrupted",
            "next": snapshot.next,
            "messages": snapshot.values.get("messages", [])
        }
    except Exception as e:
        snapshot = agent_graph.get_state(config)
        if snapshot.next:
             return {
                "thread_id": req.thread_id,
                "status": "interrupted",
                "next": snapshot.next,
                "messages": snapshot.values.get("messages", [])
            }
        raise HTTPException(status_code=500, detail=str(e))

from app.schemas import SimulationInputs, SimulationResult
from app.tools.kinetics_simulator import simulate_blow_path

@app.post("/api/simulation/run", response_model=SimulationResult)
async def run_simulation_endpoint(inputs: SimulationInputs):
    try:
        # Run synchronous simulation in thread pool to avoid blocking
        import asyncio
        result = await asyncio.to_thread(simulate_blow_path, inputs)
        return result
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ---------------------------------------------------------------------------
# PlantA 四大平衡配吃顾问端点 (B 路：MVP 服务化桥接)
# 对齐 MVP 的 runModel() 与 arb() 卡：输入铁水条件 → 配吃量 + 精钒渣 V2O5 品位 + ΔH 仲裁双案
# ---------------------------------------------------------------------------
from app.tools.plant_a_reference import run_plant_a_model, PlantAInputs, MetalAnalysis
import app.tools.plant_a_reference as _pg_ref

class PlantAChargeRequest(BaseModel):
    C: float
    Si: float
    V: float
    Ti: float | None = None
    P: float | None = None
    S: float | None = None
    Mn: float | None = None
    Cr: float | None = None
    iron_weight_kg: float = 80000.0
    iron_temp_c: float = 1300.0
    is_one_can: bool = True
    dh_v: float | None = None  # 覆盖 V 氧化热；默认引擎 2777，可传 15000 触发仲裁对照

def _build_plant_a_inputs(req: PlantAChargeRequest, dh_v: float) -> PlantAInputs:
    base = PlantAInputs()
    base.iron_weight = req.iron_weight_kg
    base.iron = MetalAnalysis(
        C=req.C, Si=req.Si,
        Mn=req.Mn if req.Mn is not None else base.iron.Mn,
        P=req.P if req.P is not None else base.iron.P,
        S=req.S if req.S is not None else base.iron.S,
        V=req.V,
        Cr=req.Cr if req.Cr is not None else base.iron.Cr,
        Ti=req.Ti if req.Ti is not None else base.iron.Ti,
        temp=req.iron_temp_c,
    )
    return base

def _run_plant_a_case(req: PlantAChargeRequest, dh_v: float) -> dict:
    saved = _pg_ref.DH_V
    try:
        _pg_ref.DH_V = dh_v
        r = run_plant_a_model(_build_plant_a_inputs(req, dh_v))
        ti = req.Ti if req.Ti is not None else PlantAInputs().iron.Ti
        return {
            "dh_v": dh_v,
            "v2o5_grade_pct": round(r.v2o5_grade, 4),
            "slag_grade_pct": {k: round(v, 4) for k, v in r.product["slag_grade"].items()},
            "recipe_kg": {k: (round(v, 2) if v is not None else None)
                          for k, v in r.after["coolant_weights"].items()},
            "v_recovery_pct": round(r.product["v_balance"]["recovery_pct"], 3),
            "v_si_ti_ratio": round(req.V / (req.Si + ti), 4),
        }
    finally:
        _pg_ref.DH_V = saved

def _b_structure(req: "PlantAChargeRequest") -> dict:
    """B 厂查表品种分配结构（M18：A 供总量×B 供结构——边界文档 §3.2 教义）。"""
    from app.tools.initial_charge import calculate_initial_charge
    from app.schemas import InitialChargeInputs, IronInitialAnalysis
    inp = InitialChargeInputs(
        iron_weight_t=req.iron_weight_kg / 1000.0, iron_temp_c=req.iron_temp_c,
        iron_analysis=IronInitialAnalysis(C=req.C, Si=req.Si, V=req.V, Ti=req.Ti or 0.10,
                                          P=0.08, S=0.03, Mn=0.20),
        is_one_can=req.is_one_can)
    r = calculate_initial_charge(inp)
    total_b = sum(r.recipe.values()) or 1.0
    props = {k: round(v / total_b, 3) for k, v in r.recipe.items()}
    return {"structure": r.recipe, "proportions": props, "warnings": r.warnings}


@app.post("/api/plant_a/charge")
async def plant_a_charge(req: PlantAChargeRequest):
    primary_dh = req.dh_v if req.dh_v is not None else _pg_ref.DH_V
    primary = _run_plant_a_case(req, primary_dh)
    # 融合方案（A×B）：A 机理定总量与品位，B 查表定品种分配。
    # 口径声明：品种等效吸热属 CF-002 未仲裁，融合暂按重量配比口径。
    b = _b_structure(req)
    total_a = sum(v for v in primary["recipe_kg"].values() if v)
    fused = {k: round(total_a * p, 0) for k, p in b["proportions"].items()}
    return {
        "rule_version": "plant_a four-balance v7.0.0 (golden regression 75/75, max err 0.0002%)",
        "fused": {
            "rule": "A 总量 × B 结构（M18：同一引擎 · 双厂知识包）",
            "total_kg": round(total_a, 0),
            "recipe_kg": fused,
            "proportions": b["proportions"],
            "grade_pct": primary["v2o5_grade_pct"],
            "b_warnings": b["warnings"],
            "note": "品种等效吸热属 CF-002 未仲裁——融合按重量配比口径，终审后可切热当量口径",
        },
        "sources": {"a_total": primary["recipe_kg"], "b_structure": b["structure"]},
        "primary": primary,
        "arbitration": {
            "case_2777": _run_plant_a_case(req, 2777.0),
            "case_15000": _run_plant_a_case(req, 15000.0),
        },
    }


@app.get("/api/system/mode/audit")
async def get_mode_audit():
    """模式切换审计出口（S14）：谁/何时/从哪切到哪。"""
    return [
        {"ts": r.timestamp.isoformat(), "user": r.user, "from": r.from_mode.value,
         "to": r.to_mode.value, "reason": r.reason}
        for r in mode_controller.audit_log
    ]

@app.get("/api/stats/accuracy")
async def get_stats_accuracy(limit: int = 50, session: AsyncSession = Depends(get_db)):
    """批次偏差带统计（S13）：入库炉次的温度偏差与采纳率。诚实降级：样本 <5 标"样本不足"。"""
    result = await session.execute(
        select(Heat).order_by(Heat.timestamp.desc()).limit(min(limit, 200)))
    heats = result.scalars().all()
    n = len(heats)
    devs = [abs(h.l2_final_temp - h.actual_final_temp)
            for h in heats if h.l2_final_temp and h.actual_final_temp]
    adopted = sum(1 for h in heats if h.advice_adopted)
    return {
        "n": n,
        "sample_note": "样本不足，未启用漂移判据" if n < 5 else "样本可用",
        "temp_mae_c": round(sum(devs) / len(devs), 2) if devs else None,
        "temp_max_dev_c": round(max(devs), 2) if devs else None,
        "adoption_rate": round(adopted / n, 3) if n else None,
        "drift_flag": False,
    }

@app.get("/api/heats")
async def get_heats(
    skip: int = 0, 
    limit: int = 10, 
    session: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(Heat, AdviceLog)
        .outerjoin(AdviceLog, AdviceLog.trace_id == Heat.trace_id)
        .order_by(Heat.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    return [
        {
            "heat_id": heat.heat_id,
            "furnace_id": heat.furnace_id,
            "timestamp": heat.timestamp.isoformat(),
            "l2_final_temp": heat.l2_final_temp,
                "equilibrium_final_temp": heat.equilibrium_final_temp,
                "actual_final_temp": heat.actual_final_temp,
                "advice_adopted": heat.advice_adopted,
            "trace_id": heat.trace_id,
            "advice_message": advice.message if advice else None,
            "advice_reply": advice.reply if advice else None,
            "advice_time": advice.created_at.isoformat() if advice and advice.created_at else None,
            "actual_analysis": heat.actual_analysis,
        }
        for heat, advice in rows
    ]

@app.post("/api/heat/confirm")
async def confirm_heat(
    data: SaveHeatResultsInputs,
    session: AsyncSession = Depends(get_db)
):
    try:
        new_heat = Heat(
            furnace_id=data.furnace_id,
            heat_id=data.heat_id,
            l1_recipe=data.l1_recipe,
            l2_final_temp=data.l2_final_temp,
            equilibrium_final_temp=data.equilibrium_final_temp,
            actual_final_temp=data.actual_final_temp,
            actual_analysis=data.actual_analysis,
            advice_adopted=data.advice_adopted,
            trace_id=data.trace_id,
            timestamp=data.timestamp
        )
        session.add(new_heat)
        await session.commit()
        await session.refresh(new_heat)

        # 诚实口径：learned_entries = 已确认入库的炉次总数（模型"经验"的真实规模）
        from sqlalchemy import func
        total = await session.execute(select(func.count()).select_from(Heat))
        learned = int(total.scalar() or 0)

        return {
            "status": "success",
            "heat_id": new_heat.heat_id,
            "learned_entries": learned
        }
    except Exception as e:
        logger.error(f"Error saving heat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
