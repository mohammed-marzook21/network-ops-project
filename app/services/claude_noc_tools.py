"""
Phase 7 C2 — Claude NOC tool definitions.

These definitions describe the trusted project capabilities Claude may request.

C2 principles:
- Claude does not query raw telecom rows directly.
- Existing API/service logic remains the source of truth.
- Tool definitions contain no business logic.
- Pipeline status is checked before operational investigation.
"""

CLAUDE_NOC_TOOLS = [
    {
        "name": "get_pipeline_status",
        "description": (
            "Check whether the network analytics pipeline is healthy and "
            "whether the available analytics data is current. "
            "Use this before making operational conclusions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_network_summary",
        "description": (
            "Return the trusted network-wide operational summary from the "
            "analytics layer, including total activity, active grids, "
            "peak hour, top grid, and effective as_of timestamp."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional analytics timestamp. If omitted, use the "
                        "existing service's effective as_of behaviour."
                    ),
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_grid_activity",
        "description": (
            "Return trusted hourly activity for a specific grid using the "
            "existing grid activity service."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                },
                "date": {
                    "type": ["string", "null"],
                    "description": "Optional date in YYYY-MM-DD format.",
                },
                "hour": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "maximum": 23,
                },
                "as_of": {
                    "type": ["string", "null"],
                },
            },
            "required": ["grid_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_hotspots",
        "description": (
            "Return ranked network hotspots using the existing trusted "
            "hotspot service. Hotspot activity is not proof of congestion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
                "as_of": {
                    "type": ["string", "null"],
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_grid_features",
        "description": (
            "Return the stored engineered ML feature vector for a grid. "
            "Features are read from the existing feature service and are "
            "not recomputed by Claude."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                }
            },
            "required": ["grid_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_anomaly_score",
        "description": (
            "Return the stored anomaly assessment for a grid and timestamp. "
            "The anomaly signal describes unusual activity and does not "
            "establish congestion, outage, fault, or capacity exhaustion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                },
                "timestamp": {
                    "type": "string",
                },
            },
            "required": ["grid_id", "timestamp"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_grid_location",
        "description": (
            "Return trusted location metadata for a grid using the existing "
            "operational-support service."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                }
            },
            "required": ["grid_id"],
            "additionalProperties": False,
        },
    },
]
