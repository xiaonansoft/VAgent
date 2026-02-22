import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logger import setup_logging
from app.db.base import get_db, init_db
from app.db.models import Heat
from app.schemas import ChatRequest, ChatResponse, SaveHeatResultsInputs

from app.mcp.data_server import build_data_router
from app.data.simulator import DataSimulator
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
    recipe: Optional[dict] = None

@app.post("/api/graph/approve")
async def approve_graph(req: ApprovalRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    
    # Update state based on action
    update = {"approval_status": "approved" if req.action == "approve" else "modified"}
    if req.action == "modify" and req.recipe:
        update["recipe"] = req.recipe
        
    await agent_graph.update_state(config, update)
    
    try:
        # Resume execution
        result = await agent_graph.ainvoke(None, config=config)
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
        select(Heat).order_by(Heat.timestamp.desc()).offset(skip).limit(limit)
    )
    heats = result.scalars().all()
    return [
        {
            "heat_id": h.heat_id,
            "furnace_id": h.furnace_id,
            "timestamp": h.timestamp.isoformat(),
            "l2_final_temp": h.l2_final_temp,
                "equilibrium_final_temp": h.equilibrium_final_temp,
                "actual_final_temp": h.actual_final_temp,
                "advice_adopted": h.advice_adopted,
            "actual_analysis": h.actual_analysis,
        }
        for h in heats
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
