import asyncio

from fastapi.testclient import TestClient

from src.core import config
from src.main import app
from src.services import gemini_adapter as gemini_adapter_module
from src.services import llm_adapter as llm_adapter_module
from src.services.groq_key_pool import get_key_pool_status, mark_key_success
from src.services.llm_adapter import LLMResult
from src.services.llm_router import generate_groq_with_key_failover


client = TestClient(app)


def _result(*, ok: bool, stage: str, text: str = "ok", status_code: int | None = 200, key_id: str = "", error_message: str = "") -> LLMResult:
    return LLMResult(
        ok=ok,
        text=text if ok else "",
        provider="groq",
        model="llama-3.1-8b-instant",
        keyId=key_id,
        statusCode=status_code,
        errorType=stage,
        errorMessage=error_message,
        stage=stage,
        rawPreview=text,
        latencyMs=5,
        attemptCount=1,
        llmUsed=ok,
    )


def _respond_payload(match_id: str = "FAILOVER_ROOM") -> dict:
    return {
        "matchId": match_id,
        "phase": "Meeting",
        "wave": 2,
        "cycle": 1,
        "botId": "player_2",
        "botName": "Player 2",
        "personality": "deflector",
        "message": "player 2 is sus",
        "latestMessage": {"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"},
        "recentChat": [{"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "humanPlayers": ["player_1", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }


def _reset_groq_keys() -> None:
    mark_key_success("groq_key_1")
    mark_key_success("groq_key_2")
    mark_key_success("groq_key_3")


def test_key_pool_loads_one_or_three_keys(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "")
    pool = get_key_pool_status()
    assert pool["keyCount"] == 1
    assert pool["keys"][0]["keyId"] == "groq_key_1"
    assert pool["keys"][0]["available"] is True

    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")
    pool = get_key_pool_status()
    assert pool["keyCount"] == 3
    assert [entry["keyId"] for entry in pool["keys"]] == ["groq_key_1", "groq_key_2", "groq_key_3"]


def test_key_failover_stops_after_primary_success(monkeypatch):
    _reset_groq_keys()
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")
    monkeypatch.setattr(config, "LLM_GROQ_KEY_FAILOVER_ENABLED", True)

    calls: list[str] = []

    async def success(prompt, **kwargs):
        calls.append(kwargs.get("key_id", ""))
        return _result(ok=True, stage="success", key_id=kwargs.get("key_id", ""))

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", success)
    outcome = asyncio.run(generate_groq_with_key_failover("ok"))
    assert outcome.ok is True
    assert calls == ["groq_key_1"]
    assert outcome.keyId == "groq_key_1"
    assert outcome.attemptCount == 1
    assert outcome.failureChain[-1]["stage"] == "success"


from src.services.gemini_adapter import mark_gemini_success as _reset_gemini


def test_gemini_primary_success_skips_groq(monkeypatch):
    _reset_groq_keys()
    _reset_gemini()
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")
    monkeypatch.setattr(config, "LLM_PROVIDER_FAILOVER_ENABLED", True)

    async def gemini_success(prompt, **kwargs):
        return _result(ok=True, stage="success", text='{"messages":["nah i was at electrical"],"reason":"ok"}', key_id="", error_message="")

    async def groq_should_not_run(prompt, **kwargs):
        raise AssertionError("Groq should not be called when Gemini succeeds")

    monkeypatch.setattr(gemini_adapter_module, "generate_chat_response", gemini_success)
    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", groq_should_not_run)

    response = client.post("/respond", json=_respond_payload("GEMINI_SUCCESS"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"] == ["nah i was at electrical"]
    assert "providerUsed=gemini" in payload["trace"]
    assert "llm_used=True" in payload["trace"]


def test_gemini_rate_limited_then_groq_key1_success(monkeypatch):
    _reset_groq_keys()
    _reset_gemini()
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")

    async def gemini_rate_limited(prompt, **kwargs):
        return _result(ok=False, stage="rate_limited", status_code=429, key_id="", error_message="rate limited")

    async def groq_success(prompt, **kwargs):
        return _result(ok=True, stage="success", text='{"messages":["task progress looked fine to me"],"reason":"ok"}', key_id=kwargs.get("key_id", "groq_key_1"))

    monkeypatch.setattr(gemini_adapter_module, "generate_chat_response", gemini_rate_limited)
    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", groq_success)

    response = client.post("/respond", json=_respond_payload("GEMINI_GROQ1"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"] == ["task progress looked fine to me"]
    assert "providerUsed=groq" in payload["trace"]
    assert "keyIdUsed=groq_key_1" in payload["trace"]
    assert "gemini:rate_limited" in payload["trace"]


def test_gemini_fails_then_groq_key2_success(monkeypatch):
    _reset_groq_keys()
    _reset_gemini()
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")

    async def gemini_model_unavailable(prompt, **kwargs):
        return _result(ok=False, stage="model_unavailable", status_code=404, key_id="", error_message="model unavailable")

    async def groq_by_key(prompt, **kwargs):
        key_id = kwargs.get("key_id", "")
        if key_id == "groq_key_1":
            return _result(ok=False, stage="rate_limited", status_code=429, key_id=key_id, error_message="too many requests")
        return _result(ok=True, stage="success", text='{"messages":["nah i was at wires"],"reason":"ok"}', key_id=key_id)

    monkeypatch.setattr(gemini_adapter_module, "generate_chat_response", gemini_model_unavailable)
    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", groq_by_key)

    response = client.post("/respond", json=_respond_payload("GEMINI_GROQ2"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"] == ["nah i was at wires"]
    assert "keyIdUsed=groq_key_2" in payload["trace"]
    assert "gemini:model_unavailable" in payload["trace"]
    assert "groq_key_1:rate_limited" in payload["trace"]


def test_all_providers_fail_respond_uses_local_fallback(monkeypatch):
    _reset_groq_keys()
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")

    async def gemini_fail(prompt, **kwargs):
        return _result(ok=False, stage="rate_limited", status_code=429, key_id="", error_message="rate limited")

    async def groq_fail(prompt, **kwargs):
        key_id = kwargs.get("key_id", "")
        return _result(ok=False, stage="timeout", status_code=None, key_id=key_id, error_message="timed out")

    monkeypatch.setattr(gemini_adapter_module, "generate_chat_response", gemini_fail)
    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", groq_fail)

    response = client.post("/respond", json=_respond_payload("ALL_FAILS"))
    assert response.status_code == 200
    data = response.json()
    assert data["respond"] is True
    assert data["messages"]
    assert "fallback_used=True" in data["trace"]
    assert "all_providers_failed" in data["trace"] or "adapter_exception" in data["trace"]


def test_key_failover_moves_to_backup_on_rate_limit(monkeypatch):
    _reset_groq_keys()
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")
    monkeypatch.setattr(config, "LLM_GROQ_KEY_FAILOVER_ENABLED", True)

    calls: list[str] = []

    async def rate_limited_then_success(prompt, **kwargs):
        key_id = kwargs.get("key_id", "")
        calls.append(key_id)
        if key_id == "groq_key_1":
            return _result(ok=False, stage="rate_limited", status_code=429, key_id=key_id, error_message="too many requests")
        return _result(ok=True, stage="success", key_id=key_id)

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", rate_limited_then_success)
    outcome = asyncio.run(generate_groq_with_key_failover("ok"))
    assert outcome.ok is True
    assert calls == ["groq_key_1", "groq_key_2"]
    assert outcome.keyId == "groq_key_2"
    assert outcome.attemptCount == 2
    assert any(entry["keyId"] == "groq_key_1" and entry["stage"] == "rate_limited" for entry in outcome.failureChain)


def test_invalid_key_is_cooled_down_and_skipped(monkeypatch):
    _reset_groq_keys()
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")
    monkeypatch.setattr(config, "LLM_GROQ_KEY_FAILOVER_ENABLED", True)
    monkeypatch.setattr(config, "LLM_GROQ_KEY_COOLDOWN_SECONDS", 600)

    first_calls: list[str] = []

    async def invalid_then_success(prompt, **kwargs):
        key_id = kwargs.get("key_id", "")
        first_calls.append(key_id)
        if key_id == "groq_key_1":
            return _result(ok=False, stage="invalid_api_key", status_code=401, key_id=key_id, error_message="bad key")
        return _result(ok=True, stage="success", key_id=key_id)

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", invalid_then_success)
    first = asyncio.run(generate_groq_with_key_failover("ok"))
    assert first.ok is True
    assert first.keyId == "groq_key_2"
    assert first_calls[:2] == ["groq_key_1", "groq_key_2"]

    second_calls: list[str] = []

    async def second_success(prompt, **kwargs):
        key_id = kwargs.get("key_id", "")
        second_calls.append(key_id)
        return _result(ok=True, stage="success", key_id=key_id)

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", second_success)
    second = asyncio.run(generate_groq_with_key_failover("ok"))
    assert second.ok is True
    assert second.keyId == "groq_key_2"
    assert second_calls == ["groq_key_2"]


def test_all_fail_respond_uses_local_fallback(monkeypatch):
    _reset_groq_keys()
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "backup-two")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "backup-three")
    monkeypatch.setattr(config, "LLM_GROQ_KEY_FAILOVER_ENABLED", True)

    async def always_fail(prompt, **kwargs):
        key_id = kwargs.get("key_id", "")
        return _result(ok=False, stage="timeout", status_code=None, key_id=key_id, error_message="timed out")

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", always_fail)
    response = client.post(
        "/respond",
        json={
            "matchId": "FAILOVER_FALLBACK",
            "phase": "Meeting",
            "wave": 2,
            "cycle": 1,
            "botId": "player_2",
            "botName": "Player 2",
            "personality": "deflector",
            "message": "player 2 is sus",
            "latestMessage": {"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"},
            "recentChat": [{"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"}],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3", "player_4"],
            "infectedPlayers": ["player_2"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["respond"] is True
    assert data["messages"]
    assert "fallback_used=True" in data["trace"]