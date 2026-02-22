from __future__ import annotations

from typing import Any, List, Optional, TypedDict, Annotated, Literal, Union
import operator
from pydantic import BaseModel
from app.core.logger import logger, generate_trace_id, get_trace_id

# LangGraph Imports
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import NodeInterrupt
import sqlite3

# --- Legacy BaseAgent (Kept for compatibility) ---
class AgentResult(BaseModel):
    agent_name: str
    role: str
    content: str
    data: Optional[Any] = None
    tool_calls: List[dict] = []
    trace_id: Optional[str] = None

class BaseAgent:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.logger = logger.getChild(name)

    async def run(self, context: dict) -> AgentResult:
        # Ensure trace_id is propagated if not already set
        tid = get_trace_id()
        if not tid:
            tid = generate_trace_id()
            
        self.logger.info(f"Agent {self.name} starting execution", extra={"context_keys": list(context.keys())})
        try:
            result = await self._execute(context)
            result.trace_id = tid
            self.logger.info(f"Agent {self.name} completed successfully")
            return result
        except Exception as e:
            self.logger.error(f"Agent {self.name} failed: {str(e)}", exc_info=True)
            raise

    async def _execute(self, context: dict) -> AgentResult:
        """Subclasses must implement this method instead of run()"""
        raise NotImplementedError

# --- LangGraph Implementation ---

class GraphState(TypedDict):
    # Inputs
    si: float
    temp: float
    is_one_can: bool
    
    # Process State
    recipe: Optional[dict]
    iron_analysis: Optional[Any]
    l2_res: Optional[Any]
    l2_eq_res: Optional[Any]
    
    # Persistent Memory (Batch-to-Batch)
    prev_slag_status: Optional[dict]
    prev_lining_heat: Optional[float]
    
    # Control Flow
    approval_status: Optional[str] # "approved", "modified"
    
    # Outputs
    messages: Annotated[list, operator.add]

async def charging_node(state: GraphState):
    from app.agents.team import ChargingAgent
    agent = ChargingAgent()
    
    # Context with memory
    ctx = {
        "si": state["si"],
        "temp": state["temp"],
        "is_one_can": state["is_one_can"],
        "prev_lining_heat": state.get("prev_lining_heat"),
        "prev_slag_status": state.get("prev_slag_status")
    }
    
    res = await agent.run(ctx)
    return {
        "recipe": res.data["recipe"], 
        "iron_analysis": res.data["iron_analysis"], 
        "messages": [f"### {res.agent_name}\n{res.content}"]
    }

async def simulation_node(state: GraphState):
    from app.agents.team import SimulationAgent
    agent = SimulationAgent()
    ctx = {
        "temp": state["temp"],
        "iron_analysis": state["iron_analysis"],
        "recipe": state["recipe"]
    }
    res = await agent.run(ctx)
    return {
        "l2_res": res.data["l2_res"], 
        "l2_eq_res": res.data["l2_eq_res"], 
        "messages": [f"### {res.agent_name}\n{res.content}"]
    }

def check_deviation(state: GraphState) -> Literal["human_approval", "critic"]:
    l2_res = state["l2_res"]
    if not l2_res:
        return "critic"
    
    final_temp = l2_res.final_temp_c
    target_temp = 1380 
    
    is_temp_deviated = abs(final_temp - target_temp) > 15
    
    if state.get("approval_status") == "approved":
        return "critic"
    
    if is_temp_deviated:
        return "human_approval"
        
    return "critic"

async def human_approval_node(state: GraphState):
    if state.get("approval_status") == "approved":
        return {"messages": ["✅ 人工审批通过，继续执行。"]}
    
    if state.get("approval_status") == "modified":
        return {"messages": ["🔄 参数已人工修正，重新仿真。"]}
        
    raise NodeInterrupt("需人工审批：温度偏差过大或收得率低。")

async def critic_node(state: GraphState):
    from app.agents.team import CriticAgent
    agent = CriticAgent()
    ctx = {
        "l2_res": state["l2_res"],
        "l2_eq_res": state["l2_eq_res"]
    }
    res = await agent.run(ctx)
    return {"messages": [f"### {res.agent_name}\n{res.content}"]}

async def save_context_node(state: GraphState):
    # Persist critical state for next heat (CheckpointSaver logic)
    # In a real system, we might parse l2_res to get actual slag/lining state.
    # Here we mock it to demonstrate the mechanism.
    return {
        "prev_slag_status": {"FeO": 15.0, "V2O5": 4.0},
        "prev_lining_heat": 120.0, # Accumulated heat units
        "messages": ["💾 批次状态已归档 (CheckpointSaver)"]
    }

# Build Graph
workflow = StateGraph(GraphState)

workflow.add_node("charging", charging_node)
workflow.add_node("simulation", simulation_node)
workflow.add_node("human_approval", human_approval_node)
workflow.add_node("critic", critic_node)
workflow.add_node("save_context", save_context_node)

workflow.add_edge(START, "charging")
workflow.add_edge("charging", "simulation")

workflow.add_conditional_edges(
    "simulation",
    check_deviation,
    {
        "human_approval": "human_approval",
        "critic": "critic"
    }
)

def route_approval(state: GraphState) -> Literal["simulation", "critic"]:
    if state.get("approval_status") == "modified":
        return "simulation"
    return "critic"

workflow.add_conditional_edges(
    "human_approval",
    route_approval,
    {
        "simulation": "simulation",
        "critic": "critic"
    }
)

workflow.add_edge("critic", "save_context")
workflow.add_edge("save_context", END)

# Memory for Checkpointing (SQLite)
# check_same_thread=False needed for FastAPI async context
conn = sqlite3.connect("vagent_checkpoints.db", check_same_thread=False)
checkpointer = SqliteSaver(conn)

agent_graph = workflow.compile(checkpointer=checkpointer)

