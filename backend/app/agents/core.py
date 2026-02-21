from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel
from app.core.logger import logger, generate_trace_id, get_trace_id

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
