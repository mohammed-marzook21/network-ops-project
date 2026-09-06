"""
Hotspot & alert routes.
Phase 4, Network Operations Predictive Intelligence Project
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.network_intelligence import AlertsResponse, HotspotsResponse
from app.services.network_intelligence_service import get_alerts, get_hotspots

router = APIRouter()


@router.get("/network/hotspots", response_model=HotspotsResponse)
def network_hotspots(
    limit: int = Query(20, ge=1, le=1000, description="Max number of hotspots to return"),
    severity: Optional[str] = Query(None, description="Optional status filter (currently only 'elevated')"),
    as_of: Optional[str] = Query(
        None, description="Optional reporting timestamp; defaults to the latest available timestamp"
    ),
):
    try:
        return get_hotspots(limit=limit, severity=severity, requested_as_of=as_of)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data source unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/network/alerts", response_model=AlertsResponse)
def network_alerts(
    limit: int = Query(20, ge=1, le=1000, description="Max number of alerts to return"),
    severity: Optional[str] = Query(None, description="Optional severity filter: 'high' or 'medium'"),
    as_of: Optional[str] = Query(
        None, description="Optional reporting timestamp; defaults to the latest available timestamp"
    ),
):
    try:
        return get_alerts(limit=limit, severity=severity, requested_as_of=as_of)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data source unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
