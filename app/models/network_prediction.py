"""
Pydantic models for API5 network risk prediction.

Phase 4, Network Operations Predictive Intelligence Project.

The request and response contracts defined here must remain stable when
ML5 replaces the stub implementation with a trained model.
"""

from pydantic import BaseModel, Field


class RiskPredictionRequest(BaseModel):
    """Input features required for network risk prediction."""

    avg_activity: float = Field(
        ...,
        ge=0,
        description="Average total network activity",
    )

    activity_growth: float = Field(
        ...,
        description="Relative growth in activity",
    )

    active_hours: int = Field(
        ...,
        ge=0,
        description="Number of hours with network activity",
    )

    peak_ratio: float = Field(
        ...,
        ge=0,
        description="Ratio of peak activity to average activity",
    )

    variability: float = Field(
        ...,
        ge=0,
        description="Coefficient of variation of network activity",
    )

    internet_share: float = Field(
        ...,
        ge=0,
        le=1,
        description="Share of total activity attributed to internet activity",
    )


class RiskPredictionResponse(BaseModel):
    """Stable response contract for network risk prediction."""

    risk_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Predicted network risk score between 0 and 1",
    )

    risk_level: str = Field(
        ...,
        description="Human-readable network risk level",
    )

    model_version: str = Field(
        ...,
        description="Version of the prediction model or stub implementation",
    )

    feature_timestamp: str | None = Field(
        None,
        description=(
            "Timestamp associated with the supplied feature vector when known; "
            "null for manually entered feature values"
        ),
    )

    explanation_note: str = Field(
        ...,
        description="Explanation of how the prediction was produced",
    )