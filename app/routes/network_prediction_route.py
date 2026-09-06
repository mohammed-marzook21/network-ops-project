"""
Network risk prediction route for API5.

Phase 4, Network Operations Predictive Intelligence Project.
"""

from fastapi import APIRouter

from app.models.network_prediction import (
    RiskPredictionRequest,
    RiskPredictionResponse,
)
from app.services.network_prediction_service import predict_network_risk


router = APIRouter()


@router.post(
    "/network/predict-risk",
    response_model=RiskPredictionResponse,
    tags=["Network Prediction"],
)
def predict_risk(
    prediction_input: RiskPredictionRequest,
):
    """
    Return a network risk prediction.

    Currently uses a stub implementation.
    ML5 will replace the internal prediction logic while preserving
    this API request and response contract.
    """

    return predict_network_risk(prediction_input)