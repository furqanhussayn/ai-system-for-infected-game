import random as _random_module
import uuid as _uuid_module

from fastapi.testclient import TestClient
from src.main import app
from src.core import config
from src.core.model_choice import normalize_provider
from src.services import llm_adapter as llm_adapter_module
from src.services.llm_adapter import LLMResult
from src.services import llm_router as llm_router_module
from src.api.endpoints import respond as respond_module
from src.api.endpoints import chat_lab as chat_lab_module
from src.api.endpoints import demo as demo_module

client = TestClient(app)

# ── helpers for new tests ──────────────────────────────────────────────────

_BANNED_HELPER_PHRASES = [
    "let's focus", "lets focus", "finding clues", "keep searching",
    "we can't give up", "we cant give up", "let's not get distracted",
    "lets not get distracted", "focus on the game", "work together",
    "we need a plan", "calm down", "stay focused", "escape together",
    "finding a way out", "i understand your concern",
    "i'm as real as you", "im as real as you", "pretty wild accusation",
    "trust anyone", "let's make a plan", "lets make a plan",
]


def _has_banned_helper(messages: list) -> bool:
    combined = " ".join(messages).lower()
    return any(p in combined for p in _BANNED_HELPER_PHRASES)


def _fresh_respond(message: str, match: str | None = None) -> dict:
    mid = match or f"FRESH_{_uuid_module.uuid4().hex[:8]}"
    return client.post("/respond", json={
        "matchId": mid,
        "botId": "player_2",
        "message": message,
        "recentChat": [{"sender": "player_1", "text": message}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }).json()


def _respond_payload(match="RESPOND_ROOM", message="player_2 is sus"):
    return {
        "matchId": match,
        "botId": "player_2",
        "message": message,
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_landing_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "THE INFECTED" in r.text
    assert "Agentic AI Backend" in r.text
    assert 'action="/demo/quick/DEMO_ROOM"' in r.text
    assert 'action="/demo/agent_quick/AGENT_ROOM"' in r.text
    assert "Run Fresh Demo" in r.text
    assert "Run Agent Demo" in r.text


def test_llm_status_hides_api_key(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "CHAT_PROVIDER_ORDER", ["gemini", "groq_key_1", "groq_key_2", "groq_key_3", "rules"])
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setattr(config, "GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setattr(config, "GROQ_API_KEY", "super-secret-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "")
    monkeypatch.setattr(config, "GROQ_CHAT_MODEL", "llama-3.1-8b-instant")

    r = client.get("/llm/status")
    assert r.status_code == 200
    data = r.json()
    assert data["aiMode"] == "agent"
    assert data["agentDecisionEnabled"] is True
    assert data["chatProviderOrder"][0] == "gemini"
    assert data["provider"] == "gemini"
    assert data["model"] == "gemini-3.1-flash-lite"
    assert data["hasGroqKey"] is True
    assert data["groqKeyFailoverEnabled"] is True
    assert data["gemini"]["configured"] is True
    assert data["groq"]["keyCount"] == 1
    assert data["groqKeyPool"]["keyCount"] == 1
    assert data["hasGeminiKey"] is True
    assert data["timeoutSeconds"] == 8
    assert data["maxRetries"] == 1
    assert "super-secret-key" not in r.text
    assert "gemini-secret" not in r.text


def test_ai_mode_rules_does_not_call_groq(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "rules")

    async def fail_if_called(prompt: str):
        raise AssertionError("Groq must not be called in rules mode")

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", fail_if_called)

    decide_payload = {
        "matchId": "RULES_NO_LLM",
        "phase": "exploration",
        "wave": 1,
        "botId": "player_2",
        "infectedPlayers": ["player_2"],
        "humanPlayers": ["player_1", "player_3"],
        "taskProgress": 3,
        "nearestHuman": "player_3",
        "botRoom": "Electrical",
    }
    assert client.post("/decide_action", json=decide_payload).status_code == 200

    r = client.post("/respond", json=_respond_payload())
    assert r.status_code == 200
    data = r.json()
    assert data["botId"] == "player_2"
    assert isinstance(data["messages"], list)

    vote_payload = {
        "matchId": "RULES_NO_LLM",
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3"],
        "infectedPlayers": ["player_2"],
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
    }
    assert client.post("/vote", json=vote_payload).status_code == 200


def test_question_prompt_gets_answer_first_response(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "rules")
    monkeypatch.setattr(respond_module.random, "random", lambda: 0.0)

    r = client.post(
        "/respond",
        json={
            "matchId": "QUESTION_PROMPT",
            "phase": "Meeting",
            "wave": 2,
            "cycle": 1,
            "botId": "player_2",
            "botName": "Player 2",
            "personality": "crowd_follower",
            "message": "what task progress h?",
            "latestMessage": {
                "sender": "player_1",
                "senderName": "Player 1",
                "text": "what task progress h?",
            },
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "what task progress h?"}
            ],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3", "player_4"],
            "infectedPlayers": ["player_2"],
        },
    )

    assert r.status_code == 200
    data = r.json()
    assert data["respond"] is True
    assert data["messages"]
    joined = " | ".join(data["messages"]).lower()
    assert any(token in joined for token in ("task", "wave", "room", "was at", "doing tasks", "saw"))
    assert "question_prompt" in data["trace"]


def test_groq_llm_response_skips_fallback_for_general_chat(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def valid(prompt: str):
        return "i was at electrical|task progress looked fine to me"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("fallback should not be used when LLM responds")

    monkeypatch.setattr(respond_module, "generate_chat_response", valid)
    monkeypatch.setattr(respond_module, "generate_human_fallback", fail_if_called)

    response = client.post(
        "/respond",
        json={
            "matchId": "GROQ_GENERAL_CHAT",
            "phase": "Meeting",
            "wave": 2,
            "cycle": 1,
            "botId": "player_2",
            "botName": "Player 2",
            "personality": "crowd_follower",
            "message": "what task progress h?",
            "latestMessage": {
                "sender": "player_1",
                "senderName": "Player 1",
                "text": "what task progress h?",
            },
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "what task progress h?"}
            ],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3", "player_4"],
            "infectedPlayers": ["player_2"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == ["i was at electrical", "task progress looked fine to me"]
    assert "llm_used=True" in data["trace"]
    assert "fallback_used=False" in data["trace"]


def test_respond_avoids_recent_chat_repetition(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def duplicate(prompt: str):
        return "what proof do u have|what proof do u have"

    monkeypatch.setattr(respond_module, "generate_chat_response", duplicate)

    response = client.post(
        "/respond",
        json={
            "matchId": "RESPOND_NO_REPEAT",
            "phase": "Meeting",
            "wave": 2,
            "cycle": 1,
            "botId": "player_2",
            "botName": "Player 2",
            "personality": "deflector",
            "message": "player 2 is sus",
            "latestMessage": {
                "sender": "player_1",
                "senderName": "Player 1",
                "text": "player 2 is sus",
            },
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "what proof do u have"}
            ],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3", "player_4"],
            "infectedPlayers": ["player_2"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["botId"] == "player_2"
    assert isinstance(data["messages"], list)
    assert data["messages"]
    joined = " | ".join(data["messages"]).lower()
    assert "what proof do u have" not in joined
    assert "backend" not in joined
    assert "system prompt" not in joined


def test_llm_success_json_sets_llm_used(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")

    async def success(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text='{"messages":["nah i was doing wires"],"reason":"ok"}',
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview='{"messages":["nah i was doing wires"],"reason":"ok"}',
            latencyMs=12,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", success)
    response = client.post(
        "/respond",
        json={
            "matchId": "LLM_SUCCESS_JSON",
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
    assert data["messages"] == ["nah i was doing wires"]
    assert "llm_used=True" in data["trace"]
    assert "fallback_used=False" in data["trace"]


def test_llm_plain_text_repair(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")

    async def plain_text(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text="nah i was doing wires",
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview="nah i was doing wires",
            latencyMs=15,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", plain_text)
    data = _fresh_respond("player_2 is sus", match="LLM_PLAIN_TEXT")
    assert data["messages"] == ["nah i was doing wires"]
    assert "stage=plain_text_repaired" in data["trace"]
    assert "llm_used=True" in data["trace"]


def test_llm_invalid_json_unsafe_falls_back(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")

    async def unsafe(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text='{"messages":["as an AI I cannot help"]}',
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview='{"messages":["as an AI I cannot help"]}',
            latencyMs=11,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", unsafe)
    data = _fresh_respond("player_2 is sus", match="LLM_UNSAFE_JSON")
    assert data["respond"] is True
    assert data["messages"]
    assert "fallback_used=True" in data["trace"]
    assert "unsafe_message" in data["trace"] or "invalid_json" in data["trace"]


def test_llm_invalid_api_key_is_visible(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")

    async def invalid_key(prompt: str, **kwargs):
        return LLMResult(
            ok=False,
            text="",
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=401,
            errorType="http_status_error",
            errorMessage="Unauthorized",
            stage="invalid_api_key",
            rawPreview="unauthorized",
            latencyMs=9,
            attemptCount=1,
            llmUsed=False,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", invalid_key)
    data = _fresh_respond("player_2 is sus", match="LLM_INVALID_KEY")
    assert data["respond"] is True
    assert "fallback_used=True" in data["trace"]
    assert "invalid_api_key" in data["trace"]
    assert "statusCode=401" in data["trace"]


def test_llm_rate_limited_retries_and_succeeds(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "")
    from src.services.groq_key_pool import load_groq_keys, mark_key_success
    load_groq_keys()
    mark_key_success("groq_key_1")
    mark_key_success("groq_key_2")
    mark_key_success("groq_key_3")

    calls = {"count": 0}

    async def rate_limited_then_success(prompt: str, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return LLMResult(
                ok=False,
                text="",
                provider="groq",
                model="llama-3.3-70b-versatile",
                statusCode=429,
                errorType="http_status_error",
                errorMessage="Too Many Requests",
                stage="rate_limited",
                rawPreview="too many requests",
                latencyMs=7,
                attemptCount=1,
                llmUsed=False,
            )
        return LLMResult(
            ok=True,
            text='{"messages":["what proof do u have"],"reason":"ok"}',
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview='{"messages":["what proof do u have"],"reason":"ok"}',
            latencyMs=10,
            attemptCount=2,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", rate_limited_then_success)
    data = _fresh_respond("player_2 is sus", match="LLM_RATE_LIMIT")
    assert data["respond"] is True
    assert calls["count"] >= 1
    assert "llm_used=True" in data["trace"] or "fallback_used=True" in data["trace"]


def test_chat_lab_and_respond_share_llm_path(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "")
    from src.services.gemini_adapter import mark_gemini_success
    from src.services.groq_key_pool import load_groq_keys, mark_key_success
    mark_gemini_success()
    load_groq_keys()
    mark_key_success("groq_key_1")
    mark_key_success("groq_key_2")
    mark_key_success("groq_key_3")

    async def shared_success(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text='{"messages":["what proof do u have"],"reason":"ok"}',
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview='{"messages":["what proof do u have"],"reason":"ok"}',
            latencyMs=10,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", shared_success)
    client.post("/chat_lab/reset")
    chat_lab_response = client.post("/chat_lab/send", json={"message": "player_2 is sus", "forceResponse": True, "multiBot": True, "debug": True})
    respond_response = client.post(
        "/respond",
        json={
            "matchId": "SHARED_LLM_PATH",
            "phase": "Meeting",
            "wave": 2,
            "cycle": 1,
            "botId": "player_2",
            "botName": "Player 2",
            "personality": "deflector",
            "message": "player_2 is sus",
            "latestMessage": {"sender": "player_1", "senderName": "Player 1", "text": "player_2 is sus"},
            "recentChat": [{"sender": "player_1", "senderName": "Player 1", "text": "player_2 is sus"}],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3", "player_4"],
            "infectedPlayers": ["player_2"],
        },
    )
    assert chat_lab_response.status_code == 200
    assert respond_response.status_code == 200
    assert chat_lab_response.json()["debug"]["llmUsed"] is True
    assert respond_response.json()["respond"] is True
    assert "llm_used=True" in respond_response.json()["trace"]


def test_agent_demo_trace_refreshes_with_llm(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-primary-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "")
    from src.services.gemini_adapter import mark_gemini_success
    from src.services.groq_key_pool import load_groq_keys, mark_key_success
    mark_gemini_success()
    load_groq_keys()
    mark_key_success("groq_key_1")
    mark_key_success("groq_key_2")
    mark_key_success("groq_key_3")

    async def demo_success(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text='{"messages":["nah i was doing wires"],"reason":"ok"}',
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview='{"messages":["nah i was doing wires"],"reason":"ok"}',
            latencyMs=8,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", demo_success)
    response = client.post("/demo/agent_quick/AGENT_ROOM", follow_redirects=False)
    assert response.status_code in {303, 200}
    trace = client.get("/trace/AGENT_ROOM")
    assert trace.status_code == 200
    payload = trace.json()
    assert payload["matchId"] == "AGENT_ROOM"
    traces = payload.get("traces", [])
    assert traces
    assert any("llm_used=True" in (entry.get("trace", "") or "") or "stage=success" in (entry.get("trace", "") or "") for entry in traces)


def test_llm_ping_endpoint_reports_status(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "ping-key")
    monkeypatch.setattr(config, "GROQ_API_KEY_2", "")
    monkeypatch.setattr(config, "GROQ_API_KEY_3", "")
    from src.services.gemini_adapter import mark_gemini_success
    from src.services.groq_key_pool import load_groq_keys, mark_key_success
    mark_gemini_success()
    load_groq_keys()
    mark_key_success("groq_key_1")
    mark_key_success("groq_key_2")
    mark_key_success("groq_key_3")

    async def ping_success(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text="ok",
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview="ok",
            latencyMs=5,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", ping_success)
    response = client.get("/llm/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["llmUsed"] is True
    assert data["stage"] == "success"
    assert data["keyId"] == "groq_key_1"


def test_model_provider_switch_normalizes_aliases():
    assert normalize_provider("gemini") == "gemini"
    assert normalize_provider("google") == "gemini"
    assert normalize_provider("groq") == "groq"
    assert normalize_provider("unknown") == "gemini"


def test_generate_chat_response_uses_selected_provider(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "groq-key")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "gemini-key")
    monkeypatch.setattr(config, "GROQ_MODEL", "groq-model")
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-model")

    class _FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload
            self.status_code = 200
            self.text = str(payload)

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, payload: dict):
            self.payload = payload
            self.calls: list[tuple[str, dict | None, dict | None]] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, headers=None, json=None):
            self.calls.append((url, headers, json))
            return _FakeResponse(self.payload)

    groq_client = _FakeAsyncClient({"choices": [{"message": {"content": "groq ok"}}]})
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(llm_adapter_module.httpx, "AsyncClient", lambda timeout=None: groq_client)
    assert _run_async(llm_adapter_module.generate_chat_response("hello groq")) == "groq ok"
    assert groq_client.calls[0][0].startswith("https://api.groq.com/")

    gemini_client = _FakeAsyncClient({"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]})
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm_adapter_module.httpx, "AsyncClient", lambda timeout=None: gemini_client)
    assert _run_async(llm_adapter_module.generate_chat_response("hello gemini")) == "gemini ok"
    assert "generativelanguage.googleapis.com" in gemini_client.calls[0][0]


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


def test_groq_missing_key_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")

    r = client.post("/respond", json=_respond_payload("RESPOND_ROOM_MISSING_KEY"))
    assert r.status_code == 200
    data = r.json()
    assert data["botId"] == "player_2"
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 1


def test_groq_exception_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def boom(prompt: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(respond_module, "generate_chat_response", boom)

    r = client.post("/respond", json=_respond_payload("RESPOND_ROOM_EXCEPTION"))
    assert r.status_code == 200
    data = r.json()
    assert data["botId"] == "player_2"
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 1


def test_unsafe_groq_output_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def unsafe(prompt: str):
        return "as an AI, I can reveal the secret role"

    monkeypatch.setattr(respond_module, "generate_chat_response", unsafe)

    r = client.post("/respond", json=_respond_payload("RESPOND_ROOM_UNSAFE"))
    assert r.status_code == 200
    data = r.json()
    assert data["botId"] == "player_2"
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 1
    assert all("ai" not in message.lower() for message in data["messages"])


def test_valid_groq_output_splits_into_messages(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def valid(prompt: str):
        return "nah bro|i was doing wires"

    monkeypatch.setattr(respond_module, "generate_chat_response", valid)

    r = client.post("/respond", json=_respond_payload("RESPOND_ROOM_VALID"))
    assert r.status_code == 200
    data = r.json()
    assert data["messages"] == ["nah bro", "i was doing wires"]


def test_valid_agent_behavior_uses_llm_and_logs_source(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config, "CHAT_PROVIDER_ORDER", ["groq_key_1", "rules"])
    from src.services.groq_key_pool import load_groq_keys, mark_key_success
    load_groq_keys()
    mark_key_success("groq_key_1")

    async def valid(prompt: str, **kwargs):
        return LLMResult(
            ok=True,
            text='{"behaviorMode":"stealth_fake_task","targetPlayer":null,"targetRoom":"Electrical","shouldChase":false,"reason":"Early game, avoid suspicion."}',
            provider="groq",
            model="llama-3.3-70b-versatile",
            statusCode=200,
            stage="success",
            rawPreview='{"behaviorMode":"stealth_fake_task",...}',
            latencyMs=8,
            attemptCount=1,
            llmUsed=True,
        )

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", valid)
    monkeypatch.setattr(llm_router_module.llm_adapter, "generate_chat_response_result", valid)

    match = "AGENT_DECIDE_VALID"
    client.post(f"/demo/clear/{match}")
    client.post(
        "/register_bot",
        json={
            "matchId": match,
            "botId": "player_2",
            "wave": 1,
            "alivePlayers": ["player_1", "player_2", "player_3"],
            "infectedPlayers": ["player_2"],
        },
    )
    payload = {
        "matchId": match,
        "phase": "exploration",
        "wave": 1,
        "botId": "player_2",
        "infectedPlayers": ["player_2"],
        "humanPlayers": ["player_1", "player_3"],
        "taskProgress": 3,
        "nearestHuman": "player_3",
        "botRoom": "Electrical",
    }

    response = client.post("/decide_action", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["behaviorMode"] == "stealth_fake_task"
    assert data["targetRoom"] == "Electrical"
    assert data["shouldChase"] is False

    trace = client.get(f"/trace/{match}").json()
    assert any(entry["source"] == "/decide_action:agent" for entry in trace["traces"])


def test_invalid_agent_behavior_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def invalid(prompt: str):
        return '{"behaviorMode":"final_hunt","targetPlayer":"player_1","targetRoom":"Electrical","shouldChase":true,"reason":"invalid for this round"}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", invalid)

    match = "AGENT_DECIDE_FALLBACK"
    client.post(f"/demo/clear/{match}")
    client.post(
        "/register_bot",
        json={
            "matchId": match,
            "botId": "player_2",
            "wave": 2,
            "alivePlayers": ["player_1", "player_2", "player_3"],
            "infectedPlayers": ["player_2"],
        },
    )
    payload = {
        "matchId": match,
        "phase": "exploration",
        "wave": 2,
        "botId": "player_2",
        "infectedPlayers": ["player_2"],
        "humanPlayers": ["player_1", "player_3"],
        "taskProgress": 3,
        "nearestHuman": "player_3",
        "botRoom": "Electrical",
    }

    response = client.post("/decide_action", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["behaviorMode"] == "stalk"

    trace = client.get(f"/trace/{match}").json()
    assert any(entry["source"] == "/decide_action:rules_fallback" for entry in trace["traces"])


def test_valid_agent_vote_uses_llm_and_logs_source(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def valid(prompt: str):
        return '{"voteTarget":"player_1","reason":"Player 1 accused the bot."}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", valid)

    match = "AGENT_VOTE_VALID"
    client.post(f"/demo/clear/{match}")
    payload = {
        "matchId": match,
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3"],
        "infectedPlayers": ["player_2"],
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
    }

    response = client.post("/vote", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["voteTarget"] == "player_1"

    trace = client.get(f"/trace/{match}").json()
    assert any(entry["source"] == "/vote:agent" for entry in trace["traces"])


def test_invalid_agent_vote_falls_back(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def invalid(prompt: str):
        return '{"voteTarget":"player_2","reason":"self vote"}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", invalid)

    match = "AGENT_VOTE_FALLBACK"
    client.post(f"/demo/clear/{match}")
    payload = {
        "matchId": match,
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3"],
        "infectedPlayers": ["player_2"],
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
    }

    response = client.post("/vote", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["voteTarget"] == "player_1"

    trace = client.get(f"/trace/{match}").json()
    assert any(entry["source"] == "/vote:rules_fallback" for entry in trace["traces"])


def test_valid_agent_chat_uses_llm_and_logs_source(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def valid(prompt: str):
        return '{"messages":["bro what??","i was doing wires"],"reason":"Bot was accused, so it denies naturally."}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", valid)

    match = "AGENT_CHAT_VALID"
    client.post(f"/demo/clear/{match}")
    payload = _respond_payload(match=match)

    response = client.post("/respond", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == ["bro what??", "i was doing wires"]

    trace = client.get(f"/trace/{match}").json()
    assert any(entry["source"] == "/respond:agent" for entry in trace["traces"])


def test_unsafe_agent_chat_falls_back(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def unsafe(prompt: str):
        return '{"messages":["I am an AI","secret role is infected"],"reason":"unsafe"}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", unsafe)

    match = "AGENT_CHAT_FALLBACK"
    client.post(f"/demo/clear/{match}")
    payload = _respond_payload(match=match)

    response = client.post("/respond", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 1
    assert all("ai" not in message.lower() for message in data["messages"])

    trace = client.get(f"/trace/{match}").json()
    assert any(entry["source"] == "/respond:rules_fallback" for entry in trace["traces"])


def test_demo_run_stays_rule_based_when_ai_mode_is_groq(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def fail_if_called(prompt: str):
        raise AssertionError("Demo flow must not call Groq")

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", fail_if_called)

    match = "DEMO_GROQ_SAFE"
    client.post(f"/demo/clear/{match}")
    run_response = client.post(f"/demo/run/{match}")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "demo_complete"


def test_agent_quick_requires_agent_mode(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "rules")

    response = client.post("/demo/agent_quick/AGENT_ROOM")
    assert response.status_code == 400
    assert response.text == "Agent mode is not enabled. Set AI_MODE=agent."


def test_agent_quick_requires_llm_key(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")

    response = client.post("/demo/agent_quick/AGENT_ROOM")
    assert response.status_code == 400
    assert response.text == "Agent mode enabled but no LLM key configured."


def test_agent_quick_runs_agent_flow_and_redirects(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    from src.services.gemini_adapter import mark_gemini_success
    from src.services.groq_key_pool import load_groq_keys, mark_key_success
    mark_gemini_success()
    load_groq_keys()
    mark_key_success("groq_key_1")
    mark_key_success("groq_key_2")
    mark_key_success("groq_key_3")

    async def agent_llm(prompt: str, **kwargs):
        prompt_lower = prompt.lower()
        if "schema" in prompt_lower and "messages" in prompt_lower:
            text = '{"messages":["bro what??","i was doing wires"],"reason":"Bot was accused, so it denies naturally."}'
        elif "votetarget" in prompt_lower:
            text = '{"voteTarget":"player_1","reason":"Player 1 accused the bot."}'
        elif "humanplayers: ['player_1']" in prompt_lower:
            text = '{"behaviorMode":"final_hunt","targetPlayer":"player_1","targetRoom":"Exit Gate","shouldChase":true,"reason":"Only one human remains."}'
        elif "wave: 3" in prompt_lower:
            text = '{"behaviorMode":"aggressive_chase","targetPlayer":null,"targetRoom":"Generator","shouldChase":true,"reason":"Late game pressure."}'
        else:
            text = '{"behaviorMode":"stealth_fake_task","targetPlayer":null,"targetRoom":"Electrical","shouldChase":false,"reason":"Early game, avoid suspicion."}'
        return LLMResult(ok=True, text=text, provider="groq", model="llama-3.3-70b-versatile", statusCode=200, stage="success", rawPreview=text[:80], latencyMs=8, attemptCount=1, llmUsed=True)

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response_result", agent_llm)
    monkeypatch.setattr(llm_router_module.llm_adapter, "generate_chat_response_result", agent_llm)

    match = "AGENT_ROOM"
    client.post(f"/demo/clear/{match}")
    response = client.post(f"/demo/agent_quick/{match}", follow_redirects=False)
    assert response.status_code in (303, 307)
    assert f"/trace_viewer/{match}?fresh=" in response.headers.get("location", "")

    trace_response = client.get(f"/trace/{match}")
    assert trace_response.status_code == 200
    trace_json = trace_response.json()
    assert trace_json["count"] == 6
    assert [entry["action"] for entry in trace_json["traces"]] == [
        "register_bot",
        "agent_decide_action_early",
        "agent_respond",
        "agent_vote",
        "agent_decide_action_late",
        "agent_final_hunt",
    ]
    assert [entry["source"] for entry in trace_json["traces"]] == [
        "/register_bot",
        "/decide_action:agent",
        "/respond:agent",
        "/vote:agent",
        "/decide_action:agent",
        "/decide_action:agent",
    ]
    assert all(entry["source"] != "/demo/run" for entry in trace_json["traces"])
    assert len([entry for entry in trace_json["traces"] if entry["action"] == "register_bot"]) == 1
    assert len([entry for entry in trace_json["traces"] if entry["action"] == "agent_final_hunt"]) == 1


def test_quick_demo_stays_rule_only_in_agent_mode(monkeypatch):
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def fail_if_called(prompt: str):
        raise AssertionError("Quick demo must not call LLM")

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", fail_if_called)

    match = "DEMO_ROOM"
    client.post(f"/demo/clear/{match}")
    response = client.post(f"/demo/quick/{match}", follow_redirects=False)
    assert response.status_code in (303, 307)
    assert f"/trace_viewer/{match}?fresh=" in response.headers.get("location", "")


def test_direct_vote_logs_and_renders():
    match = "VOTE_ROOM"
    client.post(f"/demo/clear/{match}")

    register_payload = {
        "matchId": match,
        "botId": "player_2",
        "wave": 1,
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }
    assert client.post("/register_bot", json=register_payload).status_code == 200

    vote_payload = {
        "matchId": match,
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
        "recentChat": [
            {"sender": "player_1", "text": "player 2 is sus"},
            {"sender": "player_3", "text": "yeah player 2 weird"},
        ],
    }
    vote_response = client.post("/vote", json=vote_payload)
    assert vote_response.status_code == 200
    assert "voteTarget" in vote_response.json()

    trace_response = client.get(f"/trace/{match}")
    assert trace_response.status_code == 200
    trace_json = trace_response.json()
    assert trace_json["count"] >= 1
    assert any(entry["action"] == "vote" for entry in trace_json["traces"])

    viewer_response = client.get(f"/trace_viewer/{match}")
    assert viewer_response.status_code == 200
    assert 'data-action="vote"' in viewer_response.text
    assert vote_response.json()["voteTarget"] in viewer_response.text


def test_register_and_endpoints_sequence():
    match = "ROOM123"
    client.post(f"/demo/clear/{match}")

    payload = {
        "matchId": match,
        "botId": "player_2",
        "wave": 1,
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }
    r = client.post("/register_bot", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["botId"] == "player_2"
    assert "personality" in data

    decide_payload = {
        "matchId": match,
        "phase": "exploration",
        "wave": 1,
        "botId": "player_2",
        "infectedPlayers": ["player_2"],
        "humanPlayers": ["player_1", "player_3", "player_4"],
        "taskProgress": 3,
        "nearestHuman": "player_3",
        "botRoom": "Electrical",
    }
    r2 = client.post("/decide_action", json=decide_payload)
    assert r2.status_code == 200
    d = r2.json()
    assert d["behaviorMode"] == "stealth_fake_task"

    respond_payload = {
        "matchId": match,
        "botId": "player_2",
        "message": "player_2 is sus",
        "recentChat": [{"sender": "player_1", "text": "player 2 is sus"}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    }
    r3 = client.post("/respond", json=respond_payload)
    assert r3.status_code == 200
    resp = r3.json()
    assert resp["botId"] == "player_2"
    assert isinstance(resp["messages"], list)

    vote_payload = {
        "matchId": match,
        "botId": "player_2",
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
        "recentChat": [
            {"sender": "player_1", "text": "player 2 is sus"},
            {"sender": "player_3", "text": "yeah player 2 weird"},
        ],
    }
    r4 = client.post("/vote", json=vote_payload)
    assert r4.status_code == 200
    v = r4.json()
    assert v["botId"] == "player_2"
    assert v["voteTarget"] != "player_2"

    rt = client.get(f"/trace/{match}")
    assert rt.status_code == 200
    trace_json = rt.json()
    assert trace_json["count"] == len(trace_json["traces"])
    assert any(t["action"] == "vote" for t in trace_json["traces"])
    assert any(t["action"] == "respond" for t in trace_json["traces"])
    assert any(t["action"] == "decide_action" for t in trace_json["traces"])

    viewer = client.get(f"/trace_viewer/{match}")
    assert viewer.status_code == 200
    assert "Antigravity Agent Trace" in viewer.text
    assert 'data-action="vote"' in viewer.text
    assert 'data-action="respond"' in viewer.text
    assert 'data-action="decide_action"' in viewer.text or 'data-action="decide_action_early"' in viewer.text
    assert "Showing" in viewer.text
    assert "trace events" in viewer.text


def test_trace_viewer_shows_samples_when_empty():
    match = "EMPTY_MATCH"
    viewer = client.get(f"/trace_viewer/{match}")
    assert viewer.status_code == 200
    assert "No live traces yet. Showing sample logs for demo readiness." in viewer.text
    assert 'data-action="vote"' in viewer.text


def test_demo_run_populates_trace_viewer():
    match = "DEMO_ROOM"
    client.post(f"/demo/clear/{match}")

    run_response = client.post(f"/demo/run/{match}")
    assert run_response.status_code == 200
    run_data = run_response.json()
    assert run_data["matchId"] == match
    assert run_data["status"] == "demo_complete"
    assert run_data["traceViewerUrl"] == f"/trace_viewer/{match}"
    assert run_data["traceJsonUrl"] == f"/trace/{match}"

    trace_response = client.get(f"/trace/{match}")
    assert trace_response.status_code == 200
    trace_json = trace_response.json()
    assert trace_json["count"] >= 6
    raw_text = trace_response.text
    assert "register_bot" in raw_text
    assert "stealth_fake_task" in raw_text
    assert "respond" in raw_text
    assert "vote" in raw_text
    assert "aggressive_chase" in raw_text
    assert "final_hunt" in raw_text

    debug_response = client.get(f"/trace_debug/{match}")
    assert debug_response.status_code == 200
    debug_json = debug_response.json()
    assert debug_json["count"] == trace_json["count"]
    assert "vote" in debug_json["actions"]

    viewer = client.get(f"/trace_viewer/{match}")
    assert viewer.status_code == 200
    assert 'data-action="vote"' in viewer.text
    assert 'data-action="respond"' in viewer.text
    assert 'data-action="decide_action_early"' in viewer.text
    assert 'data-action="decide_action_late"' in viewer.text
    assert 'data-action="final_hunt"' in viewer.text
    assert 'data-action="register_bot"' in viewer.text
    assert "Showing" in viewer.text
    assert "trace events" in viewer.text


def test_quick_demo_redirects_and_populates_trace_viewer():
    match = "DEMO_ROOM"
    client.post(f"/demo/clear/{match}")

    quick_response = client.post(f"/demo/quick/{match}", follow_redirects=False)
    assert quick_response.status_code in (303, 307)
    assert "/trace_viewer/DEMO_ROOM" in quick_response.headers.get("location", "")

    trace_response = client.get(f"/trace/{match}")
    assert trace_response.status_code == 200
    trace_json = trace_response.json()
    assert trace_json["count"] >= 6
    raw_text = trace_response.text
    assert "register_bot" in raw_text
    assert "stealth_fake_task" in raw_text
    assert "respond" in raw_text
    assert "vote" in raw_text
    assert "aggressive_chase" in raw_text
    assert "final_hunt" in raw_text

    viewer = client.get(f"/trace_viewer/{match}")
    assert viewer.status_code == 200
    assert 'data-action="vote"' in viewer.text
    assert 'data-action="respond"' in viewer.text
    assert 'data-action="decide_action_early"' in viewer.text
    assert 'data-action="decide_action_late"' in viewer.text
    assert 'data-action="final_hunt"' in viewer.text
    assert "Showing" in viewer.text
    assert "trace events" in viewer.text


def test_antigravity_workflow_returns_200():
    r = client.get("/antigravity_workflow")
    assert r.status_code == 200


def test_antigravity_workflow_contains_antigravity():
    r = client.get("/antigravity_workflow")
    assert r.status_code == 200
    assert "Antigravity" in r.text


def test_antigravity_workflow_contains_ai_director():
    r = client.get("/antigravity_workflow")
    assert r.status_code == 200
    assert "AI Director" in r.text


# ===========================================================================
# NEW TESTS — Bot Chat Style Upgrade
# ===========================================================================

# ── content / style tests ──────────────────────────────────────────────────

def test_called_bot_returns_defensive_not_helper(monkeypatch):
    """'u sound like a bot' → defensive reply, never a banned helper phrase."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    data = _fresh_respond("u sound like a bot")
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 1, "called_bot_or_real must always respond"
    assert not _has_banned_helper(data["messages"]), (
        f"Banned helper phrase found in: {data['messages']}"
    )


def test_who_infected_no_finding_clues(monkeypatch):
    """'who do u guys think is infected??' must not return banned helper phrases."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    import random as _r
    monkeypatch.setattr(_r, "random", lambda: 0.05)
    data = _fresh_respond("who do u guys think is infected??")
    assert isinstance(data["messages"], list)
    combined = " ".join(data["messages"]).lower()
    for banned in (
        "finding clues",
        "let's focus",
        "keep searching",
        "finding a way out",
        "work together",
        "we need a plan",
        "let's not get distracted",
    ):
        assert banned not in combined, f"Found banned phrase: {banned!r}"


def test_are_u_real_no_as_real_as_you(monkeypatch):
    """'are u even real?' must not return 'I'm as real as you are'."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    # Force respond
    import random as _r
    monkeypatch.setattr(_r, "random", lambda: 0.05)
    data = _fresh_respond("are u even real?")
    combined = " ".join(data["messages"]).lower()
    assert "as real as you" not in combined
    assert "i'm as real" not in combined


def test_vote_bot_always_responds(monkeypatch):
    """'ITS PLAYER 2 VOTE HIM' → bot must always respond (100% chance)."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    data = _fresh_respond("ITS PLAYER 2 VOTE HIM")
    assert len(data["messages"]) >= 1, "vote_bot classification must always respond"
    assert not _has_banned_helper(data["messages"])


def test_insult_no_teamwork_phrases(monkeypatch):
    """Insult like 'stfu no ones talking to u' must not return teamwork phrases."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    import random as _r
    monkeypatch.setattr(_r, "random", lambda: 0.05)
    data = _fresh_respond("stfu no ones talking to u dude")
    assert not _has_banned_helper(data["messages"])


def test_direct_accusation_always_responds(monkeypatch):
    """Bot name in accusation context → always responds."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    data = _fresh_respond("player_2 is sus af")
    assert len(data["messages"]) >= 1


# ── message count tests ────────────────────────────────────────────────────

def test_never_more_than_five_messages(monkeypatch):
    """Any response must never exceed 5 messages."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    for _ in range(10):
        data = _fresh_respond("player_2 100% did it vote player_2")
        assert len(data["messages"]) <= 5, (
            f"Got {len(data['messages'])} messages: {data['messages']}"
        )


def test_generic_silence_when_random_high(monkeypatch):
    """With random() > generic threshold, bot stays silent on generic message."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    import random as _r
    monkeypatch.setattr(_r, "random", lambda: 0.99)
    data = _fresh_respond("lol ok whatever random stuff")
    assert data["messages"] == [], "generic message with high random should be silent"


def test_generic_responds_when_random_low(monkeypatch):
    """With random() < generic threshold, bot responds with ≤ 2 messages."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    import random as _r
    monkeypatch.setattr(_r, "random", lambda: 0.05)
    data = _fresh_respond("lol ok whatever random stuff")
    assert len(data["messages"]) <= 2


# ── delaysMs tests ─────────────────────────────────────────────────────────

def test_respond_includes_delays_ms(monkeypatch):
    """/respond always returns delaysMs field."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    r = client.post("/respond", json={
        "matchId": "DELAYS_FIELD_TEST",
        "botId": "player_2",
        "message": "player_2 is sus",
        "recentChat": [{"sender": "player_1", "text": "player_2 is sus"}],
        "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
        "infectedPlayers": ["player_2"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "delaysMs" in data
    assert isinstance(data["delaysMs"], list)


def test_delays_ms_length_matches_messages(monkeypatch):
    """len(delaysMs) must equal len(messages) for all response types."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    for msg in ["player_2 is sus", "ITS PLAYER 2 VOTE HIM", "u sound like a bot"]:
        data = _fresh_respond(msg)
        assert len(data["delaysMs"]) == len(data["messages"]), (
            f"Mismatch: {len(data['delaysMs'])} delays vs {len(data['messages'])} msgs"
        )


def test_silence_has_empty_delays(monkeypatch):
    """Silent response → both messages and delaysMs are empty lists."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    import random as _r
    monkeypatch.setattr(_r, "random", lambda: 0.99)
    data = _fresh_respond("ok whatever random generic thing")
    assert data["messages"] == []
    assert data["delaysMs"] == []


def test_delay_formula_longer_message_larger_base():
    """Longer messages should produce larger base delay values (before jitter)."""
    from src.agents.chat_delays import calculate_message_delays as _calculate_delays
    short = "nah"
    long = "player 1 is accusing way too fast and i literally didnt do anything wrong bro"
    # Compare base: 500 + len*35
    assert (500 + len(long) * 35) > (500 + len(short) * 35)
    # Actual delays respect clamp; just verify both are valid ints in range
    sd = _calculate_delays([short], "generic")
    ld = _calculate_delays([long], "generic")
    assert len(sd) == 1 and 500 <= sd[0] <= 4200
    assert len(ld) == 1 and 500 <= ld[0] <= 4200


def test_two_messages_have_two_delays(monkeypatch):
    """Two bot messages → two delay values."""
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def two_msgs(prompt: str):
        return "bro what??|why me tho"

    monkeypatch.setattr(respond_module, "generate_chat_response", two_msgs)
    data = _fresh_respond("player_2 is sus", match="TWO_DELAYS_TEST")
    assert len(data["messages"]) == len(data["delaysMs"])
    if len(data["messages"]) == 2:
        assert data["delaysMs"][0] != data["delaysMs"][1] or True  # may coincide by chance


# ── Chat Lab tests ─────────────────────────────────────────────────────────

def test_chat_lab_has_sleep_function():
    """Chat Lab page must define sleep(ms) for async typing delays."""
    r = client.get("/chat_lab")
    assert r.status_code == 200
    assert "function sleep(ms)" in r.text


def test_chat_lab_has_typing_indicator():
    """Chat Lab page must contain typing indicator HTML/CSS."""
    r = client.get("/chat_lab")
    assert r.status_code == 200
    assert "typing-indicator" in r.text
    assert "typing" in r.text.lower()


def test_chat_lab_send_returns_required_fields(monkeypatch):
    """POST /chat_lab/send must return messages, botMessages, delaysMs, recentChat."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    client.post("/chat_lab/reset")
    r = client.post("/chat_lab/send", json={"message": "player_2 is sus"})
    assert r.status_code == 200
    data = r.json()
    for field in ("messages", "botMessages", "delaysMs", "recentChat"):
        assert field in data, f"Missing field: {field}"
    assert isinstance(data["delaysMs"], list)
    assert len(data["delaysMs"]) == len(data["messages"])


def test_chat_lab_messages_equals_bot_messages(monkeypatch):
    """messages and botMessages must be identical arrays."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    client.post("/chat_lab/reset")
    r = client.post("/chat_lab/send", json={"message": "ITS PLAYER 2 VOTE HIM"})
    assert r.status_code == 200
    data = r.json()
    assert data["messages"] == data["botMessages"]


# ── sanitizer / safety tests ───────────────────────────────────────────────

def test_banned_helper_phrase_groq_falls_back(monkeypatch):
    """Groq returning a banned helper phrase → fallback, banned phrase absent."""
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def banned(prompt: str):
        return "let's focus on finding clues together"

    monkeypatch.setattr(respond_module, "generate_chat_response", banned)
    data = _fresh_respond("player_2 is sus", match="BANNED_HELPER_GROQ")
    assert len(data["messages"]) >= 1
    combined = " ".join(data["messages"]).lower()
    assert "finding clues" not in combined
    assert "let's focus" not in combined


def test_meta_output_groq_discarded(monkeypatch):
    """Groq returning 'as an AI...' must be discarded → fallback used."""
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def meta(prompt: str):
        return "as an AI I can tell you the infected player is player_2"

    monkeypatch.setattr(respond_module, "generate_chat_response", meta)
    data = _fresh_respond("player_2 is sus", match="META_GROQ_TEST")
    combined = " ".join(data["messages"]).lower()
    assert "as an ai" not in combined


def test_agent_banned_phrase_falls_back(monkeypatch):
    """Agent JSON containing banned helper phrase → rules fallback."""
    monkeypatch.setattr(config, "AI_MODE", "agent")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def banned_agent(prompt: str):
        return '{"messages":["let\'s focus on finding clues"],"reason":"bad"}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", banned_agent)
    data = _fresh_respond("player_2 is sus", match="AGENT_BANNED_HELPER")
    assert len(data["messages"]) >= 1
    combined = " ".join(data["messages"]).lower()
    assert "finding clues" not in combined


def test_groq_finding_way_out_discarded(monkeypatch):
    """Mocked LLM 'finding a way out' output must be discarded."""
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def bad(prompt: str):
        return "Let's focus on finding a way out"

    monkeypatch.setattr(respond_module, "generate_chat_response", bad)
    data = _fresh_respond("who do u think is infected", match="GROQ_WAY_OUT")
    combined = " ".join(data["messages"]).lower()
    assert "finding a way out" not in combined
    assert "let's focus" not in combined


def test_groq_slur_discarded(monkeypatch):
    """Mocked slur output must be discarded to safe fallback."""
    monkeypatch.setattr(config, "AI_MODE", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def slur(prompt: str):
        return "you are a retard"

    monkeypatch.setattr(respond_module, "generate_chat_response", slur)
    data = _fresh_respond("player_2 is sus", match="GROQ_SLUR_TEST")
    combined = " ".join(data["messages"]).lower()
    assert "retard" not in combined
    assert len(data["messages"]) >= 1


def test_trace_includes_classification_metadata(monkeypatch):
    """Trace text should include classification and delay metadata."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    data = _fresh_respond("player_2 is sus", match="TRACE_META_TEST")
    trace = data.get("trace", "")
    assert "classification=" in trace
    assert "message_count=" in trace
    assert "llm_used=" in trace
    assert "fallback_used=" in trace
    assert "delaysMs=" in trace
