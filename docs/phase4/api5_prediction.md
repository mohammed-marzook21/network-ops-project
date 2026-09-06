# API5 - Network Risk Prediction Endpoint

## Phase 4 - Network Operations Predictive Intelligence Project

API5 defines the prediction API contract before the ML model is
implemented.

The purpose of this endpoint is to allow React and the Claude Network
Operations Assistant to integrate with the prediction service without
waiting for ML5.

ML5 must preserve this request and response contract when replacing the
stub implementation with a trained model.

---

# Endpoint

## POST `/network/predict-risk`

### Business Question

**What is the predicted network risk based on the supplied network
features?**

---

# Current Implementation

The current implementation is a stub.

It does not use a trained machine learning model.

The stub exists to establish and validate the API contract before ML5 is
implemented.

When ML5 introduces the trained model, the internal prediction logic may
change, but the API request and response contract must remain unchanged.

This ensures that React and other consumers do not require changes when
the real model replaces the stub.

---

# Request Contract

The endpoint accepts a JSON request body containing the following
network features:

- `avg_activity`
- `activity_growth`
- `active_hours`
- `peak_ratio`
- `variability`
- `internet_share`

## Example Request

```json
{
  "avg_activity": 412.7,
  "activity_growth": 0.183,
  "active_hours": 168,
  "peak_ratio": 6.2,
  "variability": 0.94,
  "internet_share": 0.71
}