import pytest
import asyncio
from app.agents.team import CoordinatorAgent
from app.schemas import IronInitialAnalysis

@pytest.mark.anyio
async def test_coordinator_agent_safe_mode():
    agent = CoordinatorAgent()
    
    # Context with INVALID inputs that would cause ValidationError in schemas
    # e.g. Si=6.0 (max 5.0), Temp=1700 (max 1600)
    context = {
        "si_content_pct": 6.0, 
        "iron_temp_c": 1700.0,
        "is_one_can": True,
        "simulator": None,
        "message": "Start process"
    }
    
    # Run the agent
    result = await agent.run(context)
    reply = result["reply"]
    
    # Assert Safe Mode was triggered
    assert "【安全模式】" in reply
    assert "应急配方" in reply
    assert "仿真模块未启动" in reply
    
    # Check trace_id exists
    assert result.get("trace_id") is not None
    
    # Check fallback values in response content
    assert "生铁块：5.0 吨" in reply

@pytest.mark.anyio
async def test_coordinator_agent_normal_mode():
    agent = CoordinatorAgent()
    
    # Context with VALID inputs
    context = {
        "si_content_pct": 0.28, 
        "iron_temp_c": 1350.0,
        "is_one_can": True,
        "simulator": None,
        "message": "Start process"
    }
    
    # Run the agent
    result = await agent.run(context)
    reply = result["reply"]
    
    # Assert Normal Mode
    assert "【安全模式】" not in reply
    assert "推荐配方" in reply
    assert "预计终点温度" in reply
    
    # Check trace_id exists
    assert result.get("trace_id") is not None
