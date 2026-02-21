from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas import (
    CoolantRecommendation, LanceProfile, CriticalTempResult, 
    DiagnoseLowYieldResult, ProcessData, SlagAnalysis,
    InitialChargeInputs, InitialChargeResult, 
    SimulationInputs, SimulationResult, IronInitialAnalysis
)

from ..tools.critical_temp import predict_critical_temp
from ..tools.diagnose_process_quality import diagnose_process_quality
from ..tools.initial_charge import calculate_initial_charge
from ..tools.kinetics_simulator import simulate_blow_path
from ..tools.lance_profile import recommend_lance_profile
from ..tools.thermal_balance import ThermalBalanceInputs, calculate_thermal_balance
from .jsonrpc import JsonRpcRequest, JsonRpcResponse, ToolCallParams


router = APIRouter()


def _tool_schemas() -> dict[str, dict[str, Any]]:
    return {
        "calculate_initial_charge": {
            "description": "L1 静态配料模型: 计算开吹配料与氧量 (SDM)",
            "inputSchema": InitialChargeInputs.model_json_schema(),
            "outputSchema": InitialChargeResult.model_json_schema(),
        },
        "simulate_blow_path": {
            "description": "L2 动态仿真模型: 提钒动力学微分方程推演",
            "inputSchema": SimulationInputs.model_json_schema(),
            "outputSchema": SimulationResult.model_json_schema(),
        },
        "diagnose_process_quality": {
            "description": "炉后过程诊断: 钒渣品位与收得率评估",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slag": SlagAnalysis.model_json_schema(),
                    "process": ProcessData.model_json_schema(),
                    "iron_analysis": IronInitialAnalysis.model_json_schema(),
                },
                "required": ["slag", "process"],
            },
            "outputSchema": DiagnoseLowYieldResult.model_json_schema(),
        },
        "calculate_thermal_balance": {
            "description": "热平衡与冷料推荐 (简版)",
            "inputSchema": ThermalBalanceInputs.model_json_schema(),
            "outputSchema": CoolantRecommendation.model_json_schema(),
        },
        "recommend_lance_profile": {
            "description": "供氧枪位策略建议",
            "inputSchema": {"type": "object", "properties": {"si_content_pct": {"type": "number"}}, "required": ["si_content_pct"]},
            "outputSchema": LanceProfile.model_json_schema(),
        },
        "predict_critical_temp": {
            "description": "临界温度与裕度预测 (Tc)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "v_content_pct": {"type": "number"},
                    "current_temp_c": {"type": "number"},
                },
            },
            "outputSchema": CriticalTempResult.model_json_schema(),
        },
    }


@router.post("/mcp/tools")
async def mcp_tools(req: JsonRpcRequest) -> JsonRpcResponse:
    if req.method == "tools/list":
        tools = []
        for name, meta in _tool_schemas().items():
            tools.append(
                {
                    "name": name,
                    "description": meta["description"],
                    "inputSchema": meta["inputSchema"],
                }
            )
        return JsonRpcResponse.ok(id=req.id, result={"tools": tools})

    if req.method == "tools/call":
        try:
            params = ToolCallParams.model_validate(req.params or {})
        except Exception as e:
            return JsonRpcResponse.fail(id=req.id, code=-32602, message="Invalid params", data=str(e))

        name = params.name
        args = params.arguments or {}

        try:
            if name == "calculate_initial_charge":
                inp = InitialChargeInputs.model_validate(args)
                out = calculate_initial_charge(inp)
                return JsonRpcResponse.ok(id=req.id, result={"content": out.model_dump(mode="json")})
            
            if name == "simulate_blow_path":
                inp = SimulationInputs.model_validate(args)
                out = simulate_blow_path(inp)
                return JsonRpcResponse.ok(id=req.id, result={"content": out.model_dump(mode="json")})
            
            if name == "diagnose_process_quality":
                slag = SlagAnalysis.model_validate(args.get("slag") or {})
                process = ProcessData.model_validate(args.get("process") or {})
                iron = IronInitialAnalysis.model_validate(args.get("iron_analysis")) if args.get("iron_analysis") else None
                out = diagnose_process_quality(slag=slag, process=process, iron_analysis=iron)
                return JsonRpcResponse.ok(id=req.id, result={"content": out.model_dump(mode="json")})

            if name == "calculate_thermal_balance":
                inp = ThermalBalanceInputs(**args)
                out = calculate_thermal_balance(inp)
                return JsonRpcResponse.ok(id=req.id, result={"content": out.model_dump(mode="json")})
            
            if name == "recommend_lance_profile":
                out = recommend_lance_profile(si_content_pct=float(args["si_content_pct"]))
                return JsonRpcResponse.ok(id=req.id, result={"content": out.model_dump(mode="json")})
            
            if name == "predict_critical_temp":
                out = predict_critical_temp(
                    v_content_pct=args.get("v_content_pct"),
                    current_temp_c=args.get("current_temp_c"),
                )
                return JsonRpcResponse.ok(id=req.id, result={"content": out.model_dump(mode="json")})
        except Exception as e:
            return JsonRpcResponse.fail(id=req.id, code=-32000, message="Tool execution error", data=str(e))

        return JsonRpcResponse.fail(id=req.id, code=-32601, message=f"Unknown tool: {name}")

    return JsonRpcResponse.fail(id=req.id, code=-32601, message=f"Method not found: {req.method}")
