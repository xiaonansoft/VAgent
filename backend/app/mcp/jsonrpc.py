from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JsonRpcError(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JsonRpcError | None = None

    @classmethod
    def ok(cls, *, id: str | int | None, result: Any) -> "JsonRpcResponse":
        return cls(id=id, result=result)

    @classmethod
    def fail(
        cls,
        *,
        id: str | int | None,
        code: int,
        message: str,
        data: Any | None = None,
    ) -> "JsonRpcResponse":
        return cls(id=id, error=JsonRpcError(code=code, message=message, data=data))


class ToolCallParams(BaseModel):
    name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)

