"""
Pydantic response models for the grid activity drill-down endpoint.
Phase 4, Network Operations Predictive Intelligence Project
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class GridActivityPoint(BaseModel):
    ts: str = Field(..., description="Hourly timestamp for this observation")
    hour: int = Field(..., description="Hour of day (0-23), same as dim_time.hour")
    sms_activity: float = Field(..., description="Total SMS activity for this grid/hour (sms_in + sms_out)")
    call_activity: float = Field(..., description="Total call activity for this grid/hour (call_in + call_out)")
    internet_activity: float = Field(..., description="Internet activity for this grid/hour")
    total_activity: float = Field(..., description="Total activity for this grid/hour")


class GridActivityResponse(BaseModel):
    grid_id: int = Field(..., description="The grid this response describes")
    as_of: str = Field(..., description="Effective reporting timestamp used as the upper bound for this response")
    window_start: Optional[str] = Field(
        None,
        description="Start of the trailing default window. Null when an explicit date/hour filter was used instead.",
    )
    window_end: str = Field(..., description="End of the window (equal to as_of)")
    point_count: int = Field(..., description="Number of hourly points in `series`")
    series: List[GridActivityPoint]

    class Config:
        json_schema_extra = {
            "example": {
                "grid_id": 4821,
                "as_of": "2013-11-07 23:00:00",
                "window_start": "2013-11-07 00:00:00",
                "window_end": "2013-11-07 23:00:00",
                "point_count": 24,
                "series": [
                    {
                        "ts": "2013-11-07 00:00:00",
                        "hour": 0,
                        "sms_activity": 12.4,
                        "call_activity": 8.1,
                        "internet_activity": 145.7,
                        "total_activity": 166.2,
                    }
                ],
            }
        }
