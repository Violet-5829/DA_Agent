from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., description="User's natural language question")
    conversation_id: str | None = Field(default=None, description="Multi-turn conversation ID")


class ChatResponse(BaseModel):
    answer: str = Field(..., description="自然语言回答")
    sql_or_code: str | None = Field(default=None, description="Executed SQL or code snippet")
    chart_url: str | None = Field(default=None, description="URL to generated chart image")
    reasoning_trace: list[dict[str, Any]] | None = Field(
        default=None, description="Step-by-step reasoning trace (debug mode)"
    )
    request_id: str = Field(..., description="Unique request ID for tracing")


class HealthResponse(BaseModel):
    status: str = "ok"
    db_connected: bool = False
    tables_loaded: int = 0
    metadata_summary: dict[str, list[dict[str, str]]] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str
