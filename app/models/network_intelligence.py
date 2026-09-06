"""
Pydantic response models for the hotspot and alert endpoints.
Phase 4, Network Operations Predictive Intelligence Project

risk_score / risk_level / model_version are deliberately present now,
always null, so ML6 can populate them later WITHOUT changing this
contract or breaking the React client -- adding a value to an existing
nullable field is additive, not breaking.

Do NOT use the word "congestion" anywhere in this file (field names,
descriptions, or docstrings) -- these are rule-based hotspots/alerts,
not a confirmed-congestion classifier.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class HotspotItem(BaseModel):
    grid_id: int
    ts: str = Field(..., description="Hourly timestamp this hotspot was observed at")
    hour: int
    total_activity: float
    status: str = Field(..., description="'elevated' -- this grid is currently ranked as high-activity")
    reason: str = Field(..., description="Human-readable explanation of why this grid was surfaced")

    risk_score: Optional[float] = Field(None, description="Reserved for ML6; null until a model is wired in")
    risk_level: Optional[str] = Field(None, description="Reserved for ML6; null until a model is wired in")
    model_version: Optional[str] = Field(None, description="Reserved for ML6; null until a model is wired in")

    class Config:
        json_schema_extra = {
            "example": {
                "grid_id": 5161,
                "ts": "2013-11-07 23:00:00",
                "hour": 23,
                "total_activity": 82634.11,
                "status": "elevated",
                "reason": "Ranked #1 by total network activity at this hour.",
                "risk_score": None,
                "risk_level": None,
                "model_version": None,
            }
        }


class HotspotsResponse(BaseModel):
    as_of: str
    count: int
    hotspots: List[HotspotItem]


class AlertItem(BaseModel):
    grid_id: int
    ts: str = Field(..., description="Hourly timestamp this alert was raised at")
    hour: int
    total_activity: float
    baseline_activity: float = Field(..., description="This grid's own historical average total_activity up to as_of")
    severity: str = Field(..., description="'high' or 'medium', based on standard deviations above baseline")
    reason: str

    risk_score: Optional[float] = Field(None, description="Reserved for ML6; null until a model is wired in")
    risk_level: Optional[str] = Field(None, description="Reserved for ML6; null until a model is wired in")
    model_version: Optional[str] = Field(None, description="Reserved for ML6; null until a model is wired in")

    class Config:
        json_schema_extra = {
            "example": {
                "grid_id": 5161,
                "ts": "2013-11-07 23:00:00",
                "hour": 23,
                "total_activity": 82634.11,
                "baseline_activity": 19042.55,
                "severity": "high",
                "reason": "Activity is 3.4 standard deviations above this grid's historical average (19042.6).",
                "risk_score": None,
                "risk_level": None,
                "model_version": None,
            }
        }


class AlertsResponse(BaseModel):
    as_of: str
    count: int
    alerts: List[AlertItem]
