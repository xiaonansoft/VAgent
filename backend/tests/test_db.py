import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db import Base, engine, Heat
from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_db_integration():
    # Setup: Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    unique_id = f"TEST-{uuid.uuid4().hex[:8]}"
    transport = ASGITransport(app=app)
    # Use AsyncClient to hit the endpoint
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "furnace_id": "F1",
            "heat_id": unique_id,
            "l1_recipe": {"ore": 100.0},
            "l2_final_temp": 1360.0,
            "equilibrium_final_temp": 1362.0,
            "actual_final_temp": 1365.0,
            "actual_analysis": {"V": 0.03},
            "advice_adopted": True,
            "timestamp": "2023-10-01T12:00:00"
        }
        response = await ac.post("/api/heat/confirm", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["heat_id"] == unique_id
        assert data["learned_entries"] >= 1
