from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.agents import meeting_orchestrator as orchestrator
from src.main import app
client = TestClient(app)

ALLOWED_PERSONALITIES = {"quiet", "deflector", "framer", "panicker", "crowd_follower"}
ALLOWED_BEHAVIOR_MODES = {"stealth_fake_task", "stalk", "aggressive_chase", "final_hunt", "frozen", "idle"}


def _register(match_id: str, bot_id: str, infected_players: list[str], human_players: list[str]) -> dict:
    response = client.post(
        "/register_bot",
        json={
            "matchId": match_id,
            "botId": bot_id,
            "botName": bot_id.replace("_", " ").title(),
            "wave": 1,
            "cycle": 1,
            "phase": "GasWave",
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": human_players,
            "infectedPlayers": infected_players,
            "taskProgress": 2,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_register_player_3_as_bot():
    data = _register(
        "GEN_REGISTER_P3",
        "player_3",
        ["player_3"],
        ["player_1", "player_2", "player_4"],
    )
    assert data["botId"] == "player_3"
    assert data["personality"] in ALLOWED_PERSONALITIES
    assert data["behaviorMode"] in ALLOWED_BEHAVIOR_MODES


def test_decide_action_for_player_3_targets_real_human():
    _register(
        "GEN_DECIDE_P3",
        "player_3",
        ["player_3"],
        ["player_1", "player_2", "player_4"],
    )
    response = client.post(
        "/decide_action",
        json={
            "matchId": "GEN_DECIDE_P3",
            "phase": "ExplorationB",
            "wave": 2,
            "cycle": 2,
            "botId": "player_3",
            "botName": "Player 3",
            "infectedPlayers": ["player_3"],
            "humanPlayers": ["player_1", "player_2", "player_4"],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "taskProgress": 4,
            "nearestHuman": "player_1",
            "botRoom": "Electrical",
            "nearestHumanRoom": "CentralHub",
            "secondsSinceLastSeenHuman": 3.5,
            "isFinalChase": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["botId"] == "player_3"
    assert data["behaviorMode"] in ALLOWED_BEHAVIOR_MODES
    assert data["targetPlayer"] != "player_3"
    if data["targetPlayer"] is not None:
        assert data["targetPlayer"] in {"player_1", "player_2", "player_4"}


def test_respond_for_player_4_is_generalized_and_leak_free(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_bot_state", lambda match_id, bot_id: {"personality": "quiet"})
    response = client.post(
        "/respond",
        json={
            "matchId": "GEN_RESPOND_P4",
            "phase": "Meeting",
            "wave": 2,
            "cycle": 2,
            "botId": "player_4",
            "botName": "Player 4",
            "personality": "quiet",
            "message": "player 4 is sus",
            "latestMessage": {
                "sender": "player_1",
                "senderName": "Player 1",
                "text": "player 4 is sus",
            },
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "player 4 is sus"}
            ],
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_2", "player_3"],
            "infectedPlayers": ["player_4"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["botId"] == "player_4"
    assert isinstance(data["respond"], bool)
    assert isinstance(data["messages"], list)
    assert "typingDelaySeconds" in data
    assert "secondMessageDelaySeconds" in data
    assert "trace" in data
    leaked = " ".join(data["messages"] + [data["trace"]]).lower()
    assert "chat lab" not in leaked
    assert "playground" not in leaked
    assert "backend" not in leaked
    assert "prompt" not in leaked
    assert "ai" not in leaked


def test_vote_for_player_4_avoids_self_and_infected():
    response = client.post(
        "/vote",
        json={
            "matchId": "GEN_VOTE_P4",
            "phase": "AntidoteVote",
            "wave": 2,
            "cycle": 2,
            "botId": "player_4",
            "botName": "Player 4",
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_2", "player_3"],
            "infectedPlayers": ["player_4"],
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "player 4 is sus"}
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["botId"] == "player_4"
    assert data["voteTarget"] != "player_4"
    assert data["voteTarget"] not in {"player_4"}
    assert data["voteTarget"] in {"player_1", "player_2", "player_3", None}
    if data["voteTarget"] is not None:
        assert data["voteTarget"] in ["player_1", "player_2", "player_3"]


def test_multiple_infected_bots_do_not_vote_each_other():
    response_one = client.post(
        "/vote",
        json={
            "matchId": "GEN_MULTI_INFECTED",
            "phase": "AntidoteVote",
            "wave": 3,
            "cycle": 1,
            "botId": "player_2",
            "botName": "Player 2",
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3"],
            "infectedPlayers": ["player_2", "player_4"],
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "player 2 is sus"}
            ],
        },
    )
    response_two = client.post(
        "/vote",
        json={
            "matchId": "GEN_MULTI_INFECTED",
            "phase": "AntidoteVote",
            "wave": 3,
            "cycle": 1,
            "botId": "player_4",
            "botName": "Player 4",
            "alivePlayers": ["player_1", "player_2", "player_3", "player_4"],
            "humanPlayers": ["player_1", "player_3"],
            "infectedPlayers": ["player_2", "player_4"],
            "recentChat": [
                {"sender": "player_1", "senderName": "Player 1", "text": "player 4 is sus"}
            ],
        },
    )
    assert response_one.status_code == 200
    assert response_two.status_code == 200
    data_one = response_one.json()
    data_two = response_two.json()
    assert data_one["voteTarget"] in {"player_1", "player_3"}
    assert data_two["voteTarget"] in {"player_1", "player_3"}
    assert data_one["voteTarget"] != "player_4"
    assert data_two["voteTarget"] != "player_2"


def test_core_participant_builder_is_not_player_2_special_case(monkeypatch):
    monkeypatch.setattr(orchestrator, "get_bot_state", lambda match_id, bot_id: None)
    request = SimpleNamespace(
        matchId="GEN_CORE_HELPER",
        botId="player_3",
        infectedPlayers=["player_3"],
        alivePlayers=["player_1", "player_2", "player_3", "player_4"],
        humanPlayers=["player_1", "player_2", "player_4"],
        recentChat=[],
    )
    participants = orchestrator.build_bot_participants_from_request(request)
    assert [participant.player_id for participant in participants] == ["player_3"]
    assert participants[0].personality == "crowd_follower"

    responder_plans, debug = orchestrator.select_responders(
        "player 3 is sus",
        recent_chat=[],
        request=request,
        force_response=True,
        debug=True,
    )
    assert responder_plans
    assert all(plan.botId == "player_3" for plan in responder_plans)
    assert debug["selectedResponders"] == ["player_3"]


def test_demo_sample_defaults_remain_available():
    response = client.post("/demo/run/DEMO_ROOM")
    assert response.status_code == 200
    data = response.json()
    assert any(step["result"].get("botId") == "player_2" for step in data["steps"])
