"""
Pydantic response model for the grid feature endpoint.
Phase 4, Network Operations Predictive Intelligence Project

Field names for the six ML2 features (avg_activity, activity_growth,
active_hours, peak_ratio, variability, internet_share) must match
ml/features.py character-for-character once ML2 is built for real -- a
mismatch here silently breaks ML5 and RE5 downstream. Until then, this
matches the placeholder pipeline in ml/features_placeholder.py, which
uses these exact names on purpose.
"""
from typing import Optional

from pydantic import BaseModel, Field


class GridFeaturesResponse(BaseModel):
    grid_id: int

    avg_activity: float = Field(..., description="Mean total_activity across all observed hours")
    activity_growth: Optional[float] = Field(
        None, description="Relative change in average activity from the first to the last observed date"
    )
    active_hours: int = Field(..., description="Count of hours with total_activity > 0")
    peak_ratio: Optional[float] = Field(None, description="max(total_activity) / avg_activity")
    variability: Optional[float] = Field(None, description="Coefficient of variation of total_activity (std/mean)")
    internet_share: Optional[float] = Field(None, description="avg(internet_activity) / avg(total_activity)")

    feature_timestamp: str = Field(..., description="AS_OF the stored feature snapshot reflects")
    data_quality_status: str = Field(..., description="'ok' or 'insufficient_data'")
    row_count: int = Field(..., description="Number of fact rows this snapshot was computed from")
    feature_age_hours: float = Field(
        ...,
        description=(
            "Hours between feature_timestamp and the warehouse's current AS_OF "
            "(MAX(dim_time.ts)). 0 means the stored features reflect the very "
            "latest data; a large value means the feature pipeline needs re-running."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "grid_id": 4821,
                "avg_activity": 412.7,
                "activity_growth": 0.183,
                "active_hours": 168,
                "peak_ratio": 6.2,
                "variability": 0.94,
                "internet_share": 0.71,
                "feature_timestamp": "2013-11-07 23:00:00",
                "data_quality_status": "ok",
                "row_count": 168,
                "feature_age_hours": 0.0,
            }
        }
