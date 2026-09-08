from typing import Any

from pydantic import BaseModel, Field


class ClaudeNOCRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Operational NOC question for the tool-using assistant.",
    )


class ClaudeNOCToolTrace(BaseModel):
    tool: str
    input: dict[str, Any]
    ok: bool


class ClaudeNOCResponse(BaseModel):
    answer: str
    tools_used: list[ClaudeNOCToolTrace]