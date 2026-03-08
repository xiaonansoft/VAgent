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
from pydantic import BaseModel

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize Simulator & Mode Controller
simulator = DataSimulator()
mode_controller = ModeController(simulator=simulator)

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

class ModeSwitchRequest(BaseModel):
    mode: SystemMode
    token: str = "default"
    user: str = "api_user"

@app.post("/api/system/mode")
async def set_system_mode(req: ModeSwitchRequest):
    try:
        mode_controller.switch_mode(req.mode, user=req.user, auth_token=req.token)
        return {"status": "ok", "mode": mode_controller.current_mode}
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
from langgraph.errors import GraphInterrupt

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
        
        return {
            "status": "success",
            "heat_id": new_heat.heat_id,
            "learned_entries": 1 # Mock value
        }
    except Exception as e:
        logger.error(f"Error saving heat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
