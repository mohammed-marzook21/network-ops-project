import pytest

from app.services import claude_noc_tool_executor as executor


def test_pipeline_status_dispatch(monkeypatch):
    expected = {"healthy": True}

    monkeypatch.setattr(
        executor,
        "get_pipeline_status",
        lambda: expected,
    )

    result = executor.execute_noc_tool(
        "get_pipeline_status",
        {},
    )

    assert result == expected


def test_network_summary_dispatch(monkeypatch):
    captured = {}

    def fake_summary(requested_as_of=None):
        captured["requested_as_of"] = requested_as_of
        return {"as_of": requested_as_of}

    monkeypatch.setattr(
        executor,
        "get_network_summary",
        fake_summary,
    )

    result = executor.execute_noc_tool(
        "get_network_summary",
        {"as_of": "2013-11-07 23:00:00"},
    )

    assert captured["requested_as_of"] == "2013-11-07 23:00:00"
    assert result["as_of"] == "2013-11-07 23:00:00"


def test_grid_activity_dispatch(monkeypatch):
    captured = {}

    def fake_grid_activity(
        grid_id,
        date=None,
        hour=None,
        requested_as_of=None,
    ):
        captured.update(
            {
                "grid_id": grid_id,
                "date": date,
                "hour": hour,
                "requested_as_of": requested_as_of,
            }
        )
        return {"grid_id": grid_id}

    monkeypatch.setattr(
        executor,
        "get_grid_activity",
        fake_grid_activity,
    )

    result = executor.execute_noc_tool(
        "get_grid_activity",
        {
            "grid_id": 4821,
            "date": "2013-11-07",
            "hour": 23,
            "as_of": "2013-11-07 23:00:00",
        },
    )

    assert result == {"grid_id": 4821}
    assert captured == {
        "grid_id": 4821,
        "date": "2013-11-07",
        "hour": 23,
        "requested_as_of": "2013-11-07 23:00:00",
    }


def test_hotspots_dispatch(monkeypatch):
    captured = {}

    def fake_hotspots(
        limit=20,
        severity=None,
        requested_as_of=None,
    ):
        captured["limit"] = limit
        captured["requested_as_of"] = requested_as_of
        return {"count": 1}

    monkeypatch.setattr(
        executor,
        "get_hotspots",
        fake_hotspots,
    )

    result = executor.execute_noc_tool(
        "get_hotspots",
        {
            "limit": 5,
            "as_of": "2013-11-07 23:00:00",
        },
    )

    assert result == {"count": 1}
    assert captured["limit"] == 5
    assert captured["requested_as_of"] == "2013-11-07 23:00:00"


def test_grid_features_dispatch(monkeypatch):
    monkeypatch.setattr(
        executor,
        "get_grid_features",
        lambda grid_id: {"grid_id": grid_id},
    )

    result = executor.execute_noc_tool(
        "get_grid_features",
        {"grid_id": 4857},
    )

    assert result == {"grid_id": 4857}


def test_grid_location_dispatch(monkeypatch):
    monkeypatch.setattr(
        executor,
        "get_grid_location",
        lambda grid_id: {"grid_id": grid_id},
    )

    result = executor.execute_noc_tool(
        "get_grid_location",
        {"grid_id": 4857},
    )

    assert result == {"grid_id": 4857}


def test_anomaly_dispatch(monkeypatch):
    monkeypatch.setattr(
        executor,
        "_get_anomaly_score",
        lambda grid_id, timestamp: {
            "grid_id": grid_id,
            "timestamp": timestamp,
        },
    )

    result = executor.execute_noc_tool(
        "get_anomaly_score",
        {
            "grid_id": 4857,
            "timestamp": "2013-11-07 23:00:00",
        },
    )

    assert result == {
        "grid_id": 4857,
        "timestamp": "2013-11-07 23:00:00",
    }


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError, match="Unknown C2 NOC tool"):
        executor.execute_noc_tool(
            "query_raw_telecom_data",
            {},

        )
def test_assistant_forces_pipeline_status_first(monkeypatch):
    from types import SimpleNamespace
    from app.services import claude_noc_assistant as assistant

    execution_order = []

    def fake_execute(tool_name, tool_input=None):
        execution_order.append(tool_name)

        if tool_name == "get_pipeline_status":
            return {
                "healthy": True,
                "as_of": "2013-11-07 23:00:00",
            }

        if tool_name == "get_grid_features":
            return {
                "grid_id": 4857,
                "feature_timestamp": "2013-11-07 23:00:00",
            }

        raise AssertionError(
            f"Unexpected tool executed: {tool_name}"
        )

    responses = iter([
        SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    id="tool-1",
                    name="get_grid_features",
                    input={"grid_id": 4857},
                )
            ]
        ),
        SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text=(
                        "Grid 4857 features retrieved. "
                        "[Source: get_grid_features]"
                    ),
                )
            ]
        ),
    ])

    class FakeMessages:
        def create(self, **kwargs):
            return next(responses)

    fake_client = SimpleNamespace(
        messages=FakeMessages()
    )

    monkeypatch.setattr(
        assistant,
        "execute_noc_tool",
        fake_execute,
    )

    monkeypatch.setattr(
        assistant,
        "_get_client",
        lambda: fake_client,
    )

    monkeypatch.setattr(
        assistant,
        "_get_model",
        lambda: "test-model",
    )

    result = assistant.ask_noc_assistant(
        "Investigate Grid 4857."
    )

    assert execution_order == [
        "get_pipeline_status",
        "get_grid_features",
    ]

    assert result["tools_used"][0]["tool"] == \
        "get_pipeline_status"

    assert result["tools_used"][1]["tool"] == \
        "get_grid_features"

    assert result["tools_used"][0]["ok"] is True
    assert result["tools_used"][1]["ok"] is True
def test_assistant_returns_tool_failure_as_evidence_gap(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.services import claude_noc_assistant as assistant

    captured_tool_result = {}

    def fake_execute(tool_name, tool_input=None):
        if tool_name == "get_pipeline_status":
            return {
                "healthy": True,
                "as_of": "2013-11-07 23:00:00",
            }

        if tool_name == "get_anomaly_score":
            raise RuntimeError(
                "Stored anomaly assessment unavailable"
            )

        raise AssertionError(
            f"Unexpected tool executed: {tool_name}"
        )

    call_number = 0

    class FakeMessages:
        def create(self, **kwargs):
            nonlocal call_number
            call_number += 1

            if call_number == 1:
                return SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            type="tool_use",
                            id="tool-anomaly-1",
                            name="get_anomaly_score",
                            input={
                                "grid_id": 4857,
                                "timestamp":
                                    "2013-11-07 23:00:00",
                            },
                        )
                    ]
                )

            # Capture what our application returned to Claude.
            tool_result = kwargs["messages"][-1]["content"][0]

            captured_tool_result.update(tool_result)

            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text=(
                            "The anomaly evidence is unavailable, "
                            "so no anomaly conclusion can be made. "
                            "[Source: get_anomaly_score]"
                        ),
                    )
                ]
            )

    fake_client = SimpleNamespace(
        messages=FakeMessages()
    )

    monkeypatch.setattr(
        assistant,
        "execute_noc_tool",
        fake_execute,
    )

    monkeypatch.setattr(
        assistant,
        "_get_client",
        lambda: fake_client,
    )

    monkeypatch.setattr(
        assistant,
        "_get_model",
        lambda: "test-model",
    )

    result = assistant.ask_noc_assistant(
        "Is Grid 4857 anomalous?"
    )

    assert result["tools_used"][0] == {
        "tool": "get_pipeline_status",
        "input": {},
        "ok": True,
    }

    assert result["tools_used"][1]["tool"] == \
        "get_anomaly_score"

    assert result["tools_used"][1]["ok"] is False

    assert captured_tool_result["is_error"] is True

    error_payload = json.loads(
        captured_tool_result["content"]
    )

    assert error_payload["available"] is False

    assert (
        "Stored anomaly assessment unavailable"
        in error_payload["error"]
    )

    assert "unavailable" in result["answer"].lower()