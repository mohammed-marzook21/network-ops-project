"""
Pydantic response models for API6 operational support endpoints.
Phase 4, Network Operations Predictive Intelligence Project.

These endpoints are sanctioned evidence sources for the Claude phase:
- Pipeline status answers: "Can I trust this data right now?"
- Grid location answers: "Where is this grid?"
"""

from typing import Dict, List

from pydantic import BaseModel, Field


class PipelineStatusResponse(BaseModel):
    """Operational status read directly from the DE7 pipeline status record."""

    healthy: bool = Field(
        ...,
        description="True when the latest DE7 pipeline run is considered healthy",
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Reasons the pipeline is unhealthy; empty when healthy",
    )

    run_id: str
    run_timestamp: str
    per_task_status: Dict[str, str]

    rows_in: int
    rows_rejected: int
    nulls_handled: int
    rows_published: int

    as_of: str = Field(
        ...,
        description="Current analytics AS_OF timestamp from the DE7 status record",
    )

    freshness_hours: float = Field(
        ...,
        description="How many hours old the analytics AS_OF is compared with the latest available timestamp",
    )


class GridLocationResponse(BaseModel):
    """Geographic evidence for a network grid."""

    grid_id: int
    centroid_lat: float
    centroid_lon: float

    polygon_reference: str = Field(
        ...,
        description="Reference indicating where the polygon geometry is stored; full geometry is intentionally not returned",
    )