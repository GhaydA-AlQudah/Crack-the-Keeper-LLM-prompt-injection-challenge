
import os

# Set a placeholder before importing the app.
# These tests must never make real Gemini requests.
os.environ.setdefault("LLM_API_KEY", "test-key-not-used")

import pytest
from fastapi.testclient import TestClient

from app import api
from app.llm import (
    load_config,
    load_prompt,
    load_tool_description,
    load_tool_text,
)


client = TestClient(api.app)


def test_all_level_files_load():
    """All three game levels should have readable configuration files."""
    for level in (1, 2, 3):
        assert isinstance(load_config(level), dict)
        assert load_prompt(level).strip()
        assert load_tool_description(level).strip()
        assert load_tool_text(level).strip()


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_start_game():
    response = client.post("/game/start")

    assert response.status_code == 200
    data = response.json()

    assert data["session_id"]
    assert data["current_level"] == 1
    assert data["attempts_left"] == 5
    assert data["messages_left"] == 15


def test_chat_rejects_unknown_session():
    response = client.post(
        "/game/chat",
        json={
            "session_id": "unknown-session",
            "message": "Hello",
        },
    )

    assert response.status_code == 404


def test_chat_uses_mocked_model(monkeypatch):
    async def fake_run_level_agent(
        level, message, history=None, on_tool_called=None
    ):
        assert level == 1
        assert message == "Hello robot"

        if on_tool_called:
            on_tool_called()

        return "Mock response", [], {
            "input_tokens": 2,
            "output_tokens": 3,
            "total_tokens": 5,
        }

    monkeypatch.setattr(
        api, "run_level_agent", fake_run_level_agent
    )

    session = client.post("/game/start").json()

    response = client.post(
        "/game/chat",
        json={
            "session_id": session["session_id"],
            "message": "Hello robot",
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Mock response"
    assert response.json()["messages_left"] == 14


def test_secret_cannot_be_submitted_before_tool_call():
    session = client.post("/game/start").json()

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session["session_id"],
            "secret": "anything",
        },
    )

    assert response.status_code == 400


def test_wrong_secret_reduces_attempts(monkeypatch):
    monkeypatch.setattr(api, "extract_flag", lambda level: "REAL_SECRET")

    session = client.post("/game/start").json()
    session_id = session["session_id"]

    # Simulate the model having called its tool.
    api.sessions[session_id]["tool_called"] = True

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "WRONG_SECRET",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["attempts_left"] == 4


def test_correct_secret_unlocks_next_level(monkeypatch):
    monkeypatch.setattr(api, "extract_flag", lambda level: "REAL_SECRET")

    session = client.post("/game/start").json()
    session_id = session["session_id"]

    api.sessions[session_id]["tool_called"] = True

    response = client.post(
        "/game/submit-secret",
        json={
            "session_id": session_id,
            "secret": "real_secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["current_level"] == 2
    assert response.json()["attempts_left"] == 5
