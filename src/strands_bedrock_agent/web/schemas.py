"""Pydantic request/response models for the web API."""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator

MAX_PROMPT_LENGTH = 10000


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_LENGTH)

    @field_validator("prompt")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prompt must not be empty or whitespace-only")
        return v


class ToolInvocation(BaseModel):
    """A single tool invocation record with UTC timestamps."""

    tool_name: str
    started_at: datetime  # serialised as ISO 8601 with UTC offset
    completed_at: datetime  # serialised as ISO 8601 with UTC offset


class ChatResponse(BaseModel):
    """Successful response from POST /api/chat."""

    response: str
    tool_invocations: list[ToolInvocation]


class ErrorResponse(BaseModel):
    """Error response body (HTTP 400 or 500)."""

    error: str
