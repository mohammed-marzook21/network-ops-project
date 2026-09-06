"""
API6 operational support routes.
Phase 4, Network Operations Predictive Intelligence Project.

Sanctioned evidence sources for the Claude phase.
"""

from fastapi import APIRouter, HTTPException

from app.models.operational_support import (
    GridLocationResponse,
    PipelineStatusResponse,
)
from app.services.operational_support_service import (
    get_grid_location,
    get_pipeline_status,
)


router = APIRouter()


@router.get(
    "/pipeline/status",
    response_model=PipelineStatusResponse,
    tags=["Operational Support"],
)
def pipeline_status():
    """Return the latest DE7 pipeline status as operational evidence."""

    try:
        return get_pipeline_status()

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline status source unavailable: {e}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get(
    "/network/grid/{grid_id}/location",
    response_model=GridLocationResponse,
    tags=["Operational Support"],
)
def grid_location(grid_id: int):
    """Return geographic evidence for a network grid."""

    try:
        return get_grid_location(grid_id)

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Data source unavailable: {e}",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e),
        )