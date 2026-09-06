"""
Grid activity drill-down route.
Phase 4, Network Operations Predictive Intelligence Project
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from app.models.network_grid import GridActivityResponse
from app.services.network_grid_service import UnknownGridError, get_grid_activity

router = APIRouter()


@router.get("/network/grid/{grid_id}", response_model=GridActivityResponse)
def grid_activity(
    grid_id: int = Path(..., description="Grid identifier. Valid range is 1-10000."),
    date: Optional[str] = Query(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Optional specific date, e.g. '2013-11-03'. Combine with `hour` to select one point.",
    ),
    hour: Optional[int] = Query(
        None, ge=0, le=23, description="Optional specific hour of day (0-23)."
    ),
    as_of: Optional[str] = Query(
        None,
        description=(
            "Optional reporting timestamp used as the upper bound. Defaults to the "
            "latest available timestamp in the analytics layer."
        ),
    ),
):
    try:
        return get_grid_activity(grid_id, date=date, hour=hour, requested_as_of=as_of)
    except UnknownGridError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data source unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
