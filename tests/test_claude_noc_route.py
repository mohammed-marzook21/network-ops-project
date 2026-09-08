from fastapi.testclient import TestClient

from app.main import app
from app.routes import claude_noc_route


client = TestClient(app)


def test_claude_noc_route_success(monkeypatch):
    monkeypatch.setattr(
        claude_noc_route,
        "ask_noc_assistant",
        lambda question: {
            "answer": (
                "Pipeline healthy. "
                "[Source: get_pipeline_status]"
            ),
            "tools_used": [
                {
                    "tool": "get_pipeline_status",
                    "input": {},
                    "ok": True,
                }
            ],
        },
    )

    response = client.post(
        "/network/assistant",
        json={
            "question": "What is the network status?"
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == (
        "Pipeline healthy. "
        "[Source: get_pipeline_status]"
    )

    assert body["tools_used"] == [
        {
            "tool": "get_pipeline_status",
            "input": {},
            "ok": True,
        }
    ]


def test_claude_noc_route_rejects_empty_question():
    response = client.post(
        "/network/assistant",
        json={"question": ""},
    )

    assert response.status_code == 422


def test_claude_noc_route_returns_clear_500(monkeypatch):
    def fail_assistant(question):
        raise RuntimeError("simulated Claude failure")

    monkeypatch.setattr(
        claude_noc_route,
        "ask_noc_assistant",
        fail_assistant,
    )

    response = client.post(
        "/network/assistant",
        json={
            "question": "Investigate Grid 4857"
        },
    )

    assert response.status_code == 500

    assert (
        "Claude NOC assistant failed"
        in response.json()["detail"]
    )

    assert (
        "simulated Claude failure"
        in response.json()["detail"]
    )