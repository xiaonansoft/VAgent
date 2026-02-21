from __future__ import annotations

import json
from typing import Any
import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..data.simulator import DataSimulator
from .jsonrpc import JsonRpcRequest, JsonRpcResponse


def build_data_router(*, simulator: DataSimulator) -> APIRouter:
    router = APIRouter()

    @router.get("/stream")
    async def stream_data(req: Request):
        async def event_generator():
            while True:
                # Get latest payload
                payload = simulator._build_payload(1.0)
                yield {
                    "data": json.dumps(payload)
                }
                await asyncio.sleep(1.0)

        return EventSourceResponse(event_generator())

    @router.post("/mcp/data")
    async def mcp_data(req: JsonRpcRequest) -> JsonRpcResponse:
        if req.method == "resources/list":
            resources = [
                {
                    "uri": "resource://plc/iron_ladle/temperature",
                    "name": "铁水温度",
                    "description": "实时铁水温度（模拟）",
                    "mimeType": "application/json",
                },
                {
                    "uri": "resource://plc/converter/lance_height",
                    "name": "枪位高度",
                    "description": "实时供氧枪位（模拟）",
                    "mimeType": "application/json",
                },
            ]
            return JsonRpcResponse.ok(id=req.id, result={"resources": resources})

        if req.method == "resources/read":
            params = req.params or {}
            uri = params.get("uri")
            if uri == "resource://plc/iron_ladle/temperature":
                return JsonRpcResponse.ok(
                    id=req.id,
                    result={
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps({"value": simulator.state.temp_c, "unit": "C"}, ensure_ascii=False),
                            }
                        ]
                    },
                )
            if uri == "resource://plc/converter/lance_height":
                return JsonRpcResponse.ok(
                    id=req.id,
                    result={
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps({"value": simulator.state.lance_height_mm, "unit": "mm"}, ensure_ascii=False),
                            }
                        ]
                    },
                )
            return JsonRpcResponse.fail(id=req.id, code=-32602, message="Unknown resource uri", data=uri)

        if req.method == "resources/subscribe":
            params = req.params or {}
            uri = params.get("uri")
            if uri not in ("resource://plc/iron_ladle/temperature", "resource://plc/converter/lance_height"):
                return JsonRpcResponse.fail(id=req.id, code=-32602, message="Unknown resource uri", data=uri)
            return JsonRpcResponse.ok(
                id=req.id,
                result={"subscription": uri, "streamUrl": "/api/stream"},
            )
        
        if req.method == "control/stop":
            simulator.emergency_stop()
            return JsonRpcResponse.ok(id=req.id, result={"status": "emergency_stop_triggered"})
            
        if req.method == "control/resume":
            simulator.resume()
            return JsonRpcResponse.ok(id=req.id, result={"status": "resumed"})

        return JsonRpcResponse.fail(id=req.id, code=-32601, message=f"Method not found: {req.method}")

    return router
