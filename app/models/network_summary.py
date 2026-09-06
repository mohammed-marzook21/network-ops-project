"""
Pydantic response models.
Phase 4, Network Operations Predictive Intelligence Project
"""

from pydantic import BaseModel, Field


class NetworkSummaryResponse(BaseModel):
    total_activity: float = Field(..., description="Sum of total_activity across all grids, up to as_of")
    active_grids: int = Field(..., description="Count of distinct grid_id with activity > 0, up to as_of")
    peak_hour: int = Field(..., description="The hour (0-23) with the highest total activity, up to as_of")
    top_grid: int = Field(..., description="The grid_id with the highest total activity, up to as_of")
    as_of: str = Field(..., description="The effective reporting timestamp used for this response")

    class Config:
        json_schema_extra = {
            "example": {
                "total_activity": 95727626.12,
                "active_grids": 10000,
                "peak_hour": 17,
                "top_grid": 5161,
                "as_of": "2013-11-02 23:00:00",
            }
        }