from fastapi import APIRouter, HTTPException

from app.models.claude_noc import (
    ClaudeNOCRequest,
    ClaudeNOCResponse,
)
from app.services.claude_noc_assistant import ask_noc_assistant


router = APIRouter(
    prefix="/network",
    tags=["Claude NOC Assistant"],
)


@router.post(
    "/assistant",
    response_model=ClaudeNOCResponse,
    summary="Ask the tool-using Claude NOC assistant",
)
def ask_network_assistant(
    request: ClaudeNOCRequest,
) -> ClaudeNOCResponse:
    """
    Answer an operational NOC question using the Phase 7 C2
    tool-using Claude assistant.

    Pipeline status is checked before Claude performs the
    investigation, and factual network evidence comes from
    trusted project tools.
    """

    try:
        result = ask_noc_assistant(request.question)

        return ClaudeNOCResponse(**result)

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Claude NOC assistant failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc