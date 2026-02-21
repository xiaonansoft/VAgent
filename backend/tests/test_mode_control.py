import pytest
import asyncio
from app.core.mode_control import ModeController, SystemMode, ValidationControlWriter, SimulationControlWriter, ProductionControlWriter

@pytest.mark.asyncio
async def test_initial_mode_is_simulation():
    controller = ModeController()
    assert controller.current_mode == SystemMode.SIMULATION
    assert isinstance(controller.writer, SimulationControlWriter)

@pytest.mark.asyncio
async def test_mode_switch_audit():
    controller = ModeController()
    await controller.switch_mode(SystemMode.VALIDATION, user="admin", auth_token="any", reason="Testing")
    
    assert controller.current_mode == SystemMode.VALIDATION
    assert len(controller.audit_log) == 1
    assert controller.audit_log[0].user == "admin"
    assert controller.audit_log[0].to_mode == SystemMode.VALIDATION

@pytest.mark.asyncio
async def test_validation_mode_isolation():
    """
    Test that Validation Mode writes to log and does NOT touch DCS (implied by class type).
    """
    controller = ModeController()
    await controller.switch_mode(SystemMode.VALIDATION, user="qa", auth_token="any")
    
    assert isinstance(controller.writer, ValidationControlWriter)
    
    # Execute a command
    await controller.writer.set_lance_height(1500.0)
    
    # Check logs (ValidationControlWriter specific)
    assert len(controller.writer.logs) == 1
    assert "Would set lance height to 1500.0mm" in controller.writer.logs[0]

@pytest.mark.asyncio
async def test_production_mode_safeguards():
    """
    Test that switching to Production requires valid token.
    """
    controller = ModeController()
    
    # Need to go via Validation first to avoid "Sim -> Prod" error
    await controller.switch_mode(SystemMode.VALIDATION, user="user", auth_token="any")
    await asyncio.sleep(1.1) # Wait for cooldown

    # Attempt with wrong token
    with pytest.raises(PermissionError):
        await controller.switch_mode(SystemMode.PRODUCTION, user="hacker", auth_token="wrong_token")
    
    await asyncio.sleep(1.1) # Wait for cooldown
    
    # Attempt with correct token
    await controller.switch_mode(SystemMode.PRODUCTION, user="plant_manager", auth_token="SECURE_PRODUCTION_TOKEN_2026")
    assert controller.current_mode == SystemMode.PRODUCTION
    assert isinstance(controller.writer, ProductionControlWriter)

@pytest.mark.asyncio
async def test_simulation_mode_uses_simulator():
    controller = ModeController()
    # Ensure we are in sim
    assert controller.current_mode == SystemMode.SIMULATION
    
    # Change simulator state via writer
    await controller.writer.set_lance_height(1234.5)
    
    # Verify reader sees the change (closed loop in simulation)
    height = await controller.reader.get_lance_height()
    assert height == 1234.5

@pytest.mark.asyncio
async def test_illegal_state_transition():
    """
    Test that switching directly from SIMULATION to PRODUCTION is forbidden.
    """
    controller = ModeController()
    with pytest.raises(ValueError, match="Illegal State Transition"):
        await controller.switch_mode(SystemMode.PRODUCTION, user="admin", auth_token="SECURE_PRODUCTION_TOKEN_2026")

@pytest.mark.asyncio
async def test_rate_limiting():
    """
    Test that rapid mode switches are rejected.
    """
    controller = ModeController()
    await controller.switch_mode(SystemMode.VALIDATION, user="admin", auth_token="any")
    
    # Immediate switch back should fail
    with pytest.raises(RuntimeError, match="Mode switch too frequent"):
        await controller.switch_mode(SystemMode.SIMULATION, user="admin", auth_token="any")
    
    # Wait and try again
    await asyncio.sleep(1.1)
    await controller.switch_mode(SystemMode.SIMULATION, user="admin", auth_token="any")
    assert controller.current_mode == SystemMode.SIMULATION
