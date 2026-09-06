"""
Grid feature-serving route.
Phase 4, Network Operations Predictive Intelligence Project
"""
from fastapi import APIRouter, HTTPException, Path

from app.models.network_features import GridFeaturesResponse
from app.services.network_features_service import FeaturesNotFoundError, get_grid_features
from app.services.network_grid_service import UnknownGridError

router = APIRouter()


@router.get("/network/grid/{grid_id}/features", response_model=GridFeaturesResponse)
def grid_features(
    grid_id: int = Path(..., description="Grid identifier. Valid range is 1-10000."),
):
    try:
        return get_grid_features(grid_id)
    except UnknownGridError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeaturesNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data source unavailable: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
