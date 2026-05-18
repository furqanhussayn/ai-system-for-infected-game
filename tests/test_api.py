from fastapi.testclient import TestClient
from src.main import app
from src.core import config
from src.services import llm_adapter as llm_adapter_module
from src.api.endpoints import respond as respond_module

client = TestClient(app)


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
    monkeypatch.setattr(config, "AI_MODE", "rules")
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "super-secret-key")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile")

    r = client.get("/llm/status")
    assert r.status_code == 200
    data = r.json()
    assert data == {
        "aiMode": "rules",
        "agentDecisionEnabled": False,
        "provider": "groq",
        "hasGroqKey": True,
        "hasGeminiKey": False,
    }
    assert "super-secret-key" not in r.text


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
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def valid(prompt: str):
        return '{"behaviorMode":"stealth_fake_task","targetPlayer":null,"targetRoom":"Electrical","shouldChase":false,"reason":"Early game, avoid suspicion."}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", valid)

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
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")

    async def agent_llm(prompt: str):
        prompt_lower = prompt.lower()
        if "schema" in prompt_lower and "messages" in prompt_lower:
            return '{"messages":["bro what??","i was doing wires"],"reason":"Bot was accused, so it denies naturally."}'
        if "votetarget" in prompt_lower:
            return '{"voteTarget":"player_1","reason":"Player 1 accused the bot."}'
        if "humanplayers: ['player_1']" in prompt_lower:
            return '{"behaviorMode":"final_hunt","targetPlayer":"player_1","targetRoom":"Exit Gate","shouldChase":true,"reason":"Only one human remains."}'
        if "wave: 3" in prompt_lower:
            return '{"behaviorMode":"aggressive_chase","targetPlayer":null,"targetRoom":"Generator","shouldChase":true,"reason":"Late game pressure."}'
        return '{"behaviorMode":"stealth_fake_task","targetPlayer":null,"targetRoom":"Electrical","shouldChase":false,"reason":"Early game, avoid suspicion."}'

    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", agent_llm)

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
