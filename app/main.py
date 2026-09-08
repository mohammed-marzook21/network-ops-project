"""
FastAPI application entry point.
Phase 4, Network Operations Predictive Intelligence Project
"""
from app.routes.network_grid_route import router as network_grid_router
from app.routes.network_intelligence_route import router as network_intelligence_router
from fastapi import FastAPI
from app.routes.network_features_route import router as network_features_router
from app.routes.network_summary_route import router as network_summary_router
from app.routes.operational_support_route import router as operational_support_router
from app.routes.network_prediction_route import router as network_prediction_router
from fastapi.middleware.cors import CORSMiddleware
from app.routes.claude_noc_route import router as claude_noc_router
app = FastAPI(
    title="Network Operations API",
    description=(
        "API layer for Network Operations analytics "
        "and predictive intelligence."
    ),
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(network_prediction_router)
app.include_router(network_summary_router)
app.include_router(network_features_router)
app.include_router(network_grid_router)
app.include_router(network_intelligence_router)
app.include_router(operational_support_router)
app.include_router(claude_noc_router)
@app.get(
    "/",
    summary="API health check",
)
def root():
    return {
        "status": "ok",
        "message": "Network Operations API is running",
    }