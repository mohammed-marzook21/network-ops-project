"""
Network summary route.
Phase 4, Network Operations Predictive Intelligence Project
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from app.models.network_summary import NetworkSummaryResponse
from app.services.network_summary_service import get_network_summary

router = APIRouter()


@router.get("/network/summary", response_model=NetworkSummaryResponse)
def network_summary(
    as_of: Optional[str] = Query(
        None,
        description="Optional reporting timestamp (e.g. '2013-11-01 12:00:00'). "
                    "Defaults to the latest available timestamp in the analytics layer.",
    )
):
    try:
        result = get_network_summary(requested_as_of=as_of)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data source unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))