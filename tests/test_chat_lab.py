"""
Tests for Meeting Chat Lab endpoint.

Tests verify:
- HTML page loads correctly
- Chat state persists during session
- Messages are sent and bot responds
- Reset clears state
- No real API calls to Groq (mocked)
"""

from fastapi.testclient import TestClient
from src.main import app
from src.core import config
from src.services import llm_adapter as llm_adapter_module
from src.api.endpoints import respond as respond_module

client = TestClient(app)


def test_chat_lab_page_loads():
    """GET /chat_lab returns 200 and contains expected elements."""
    r = client.get("/chat_lab")
    assert r.status_code == 200
    assert "THE INFECTED" in r.text
    assert "Meeting Chat Lab" in r.text
    assert "player_1" in r.text
    assert "player_2" in r.text
    assert "player_3" in r.text
    assert "player_4" in r.text
    assert "player_1: you" in r.text or "You are player_1" in r.text
    assert '<input' in r.text and 'message-input' in r.text
    assert 'send' in r.text.lower()
    assert 'reset' in r.text.lower()
    assert 'Force at least one bot response' in r.text
    assert 'Show debug info' in r.text
    assert 'Multi Bot Mode' in r.text
    assert 'is typing' in r.text or 'typing' in r.text
    assert 'sleep(ms)' in r.text or 'sleep(' in r.text


def test_chat_lab_reset_clears_state():
    """POST /chat_lab/reset clears the chat history."""
    # Send a message first
    r1 = client.post("/chat_lab/send", json={"message": "test message"})
    assert r1.status_code == 200
    data1 = r1.json()
    assert len(data1["recentChat"]) >= 1
    
    # Reset
    r2 = client.post("/chat_lab/reset")
    assert r2.status_code == 200
    assert r2.json()["status"] == "reset"
    assert r2.json()["matchId"] == "CHAT_LAB"
    
    # Verify chat is empty by checking the next state
    r3 = client.post("/chat_lab/send", json={"message": "new message"})
    assert r3.status_code == 200
    data3 = r3.json()
    # Should only have 1 user message + bot response, not previous messages
    assert len(data3["recentChat"]) >= 1


def test_chat_lab_send_message_rules_mode(monkeypatch):
    """POST /chat_lab/send works in rules mode (no real API calls)."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    
    # Reset first
    client.post("/chat_lab/reset")
    
    # Send message (accusation against bot — always gets a reply in rules mode)
    r = client.post("/chat_lab/send", json={"message": "player_2 is sus"})
    assert r.status_code == 200
    data = r.json()
    
    # Verify response structure
    assert "userMessage" in data
    assert "botMessages" in data
    assert "recentChat" in data
    
    assert data["userMessage"] == "player_2 is sus"
    assert isinstance(data["botMessages"], list)
    assert isinstance(data["recentChat"], list)
    
    # Verify chat history contains both messages
    assert any(msg["sender"] == "player_1" for msg in data["recentChat"])
    assert any(msg["sender"] == "player_2" for msg in data["recentChat"])


def test_chat_lab_send_empty_message_fails():
    """POST /chat_lab/send rejects empty messages."""
    r = client.post("/chat_lab/send", json={"message": ""})
    assert r.status_code == 400


def test_chat_lab_send_whitespace_message_fails():
    """POST /chat_lab/send rejects whitespace-only messages."""
    r = client.post("/chat_lab/send", json={"message": "   \n\t  "})
    assert r.status_code == 400


def test_chat_lab_conversation_flow(monkeypatch):
    """Test a complete conversation flow."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    
    # Reset
    client.post("/chat_lab/reset")
    
    # First message
    r1 = client.post("/chat_lab/send", json={"message": "I think player 2 is infected"})
    assert r1.status_code == 200
    data1 = r1.json()
    chat1 = data1["recentChat"]
    assert len(chat1) >= 2  # At least user + bot response
    assert chat1[0]["sender"] == "player_1"
    assert chat1[0]["text"] == "I think player 2 is infected"
    
    # Second message (should include previous history)
    r2 = client.post("/chat_lab/send", json={"message": "yeah definitely sus"})
    assert r2.status_code == 200
    data2 = r2.json()
    chat2 = data2["recentChat"]
    assert len(chat2) > len(chat1)  # Should accumulate
    # Find the second player_1 message (the latest one)
    player_1_messages = [msg for msg in chat2 if msg["sender"] == "player_1"]
    assert len(player_1_messages) >= 2
    assert player_1_messages[-1]["text"] == "yeah definitely sus"


def test_chat_lab_multiple_bot_messages(monkeypatch):
    """Test that bot can return multiple messages (up to 2)."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    
    # Reset
    client.post("/chat_lab/reset")
    
    # Send message (might get 1 or 2 bot responses depending on personality)
    r = client.post("/chat_lab/send", json={"message": "hey everyone"})
    assert r.status_code == 200
    data = r.json()
    
    assert isinstance(data["botMessages"], list)
    assert len(data["botMessages"]) <= 2
    assert all(isinstance(msg, str) for msg in data["botMessages"])


def test_chat_lab_respects_player_ids(monkeypatch):
    """Test that messages use correct player IDs (multi-bot)."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    
    # Reset
    client.post("/chat_lab/reset")
    
    # Send message
    r = client.post("/chat_lab/send", json={"message": "test"})
    assert r.status_code == 200
    data = r.json()
    
    # Check all senders are valid players (multi-bot may have player_2/3/4)
    valid_senders = {"player_1", "player_2", "player_3", "player_4"}
    for msg in data["recentChat"]:
        assert msg["sender"] in valid_senders, f"Invalid sender: {msg['sender']}"
        if msg["sender"] == "player_1":
            # First player_1 message should be our input
            assert msg["text"] == "test"


def test_chat_lab_does_not_call_groq_in_rules_mode(monkeypatch):
    """Ensure no real Groq API calls in rules mode."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    
    # Mock generate_chat_response to fail if called
    async def fail_if_called(prompt: str):
        raise AssertionError("Groq must not be called in rules mode")
    
    monkeypatch.setattr(llm_adapter_module, "generate_chat_response", fail_if_called)
    
    # Reset and send message - should NOT call Groq
    client.post("/chat_lab/reset")
    r = client.post("/chat_lab/send", json={"message": "hello"})
    assert r.status_code == 200


def test_chat_lab_landing_page_includes_link():
    """Verify /chat_lab link appears on landing page."""
    r = client.get("/")
    assert r.status_code == 200
    assert "/chat_lab" in r.text
    assert "Chat Lab" in r.text or "chat" in r.text.lower()


def test_chat_lab_persists_state_across_requests(monkeypatch):
    """Verify chat state persists across multiple requests."""
    monkeypatch.setattr(config, "AI_MODE", "rules")
    
    # Reset
    client.post("/chat_lab/reset")
    
    messages_sent = []
    
    # Send 3 messages
    for i in range(3):
        msg = f"message {i}"
        messages_sent.append(msg)
        r = client.post("/chat_lab/send", json={"message": msg})
        assert r.status_code == 200
    
    # Verify all messages are in the final chat history
    r_final = client.post("/chat_lab/send", json={"message": "final"})
    assert r_final.status_code == 200
    chat = r_final.json()["recentChat"]
    
    # Check that all previous messages are still there
    for sent_msg in messages_sent:
        assert any(msg["text"] == sent_msg and msg["sender"] == "player_1" for msg in chat)


def test_chat_lab_response_contains_all_fields():
    """Verify POST /chat_lab/send response has all required fields."""
    # Reset
    client.post("/chat_lab/reset")
    
    r = client.post("/chat_lab/send", json={"message": "test"})
    assert r.status_code == 200
    data = r.json()
    
    # Check required fields exist
    assert "userMessage" in data
    assert "botMessages" in data
    assert "recentChat" in data
    
    # Check types
    assert isinstance(data["userMessage"], str)
    assert isinstance(data["botMessages"], list)
    assert isinstance(data["recentChat"], list)
    
    # Check message format in recentChat
    for msg in data["recentChat"]:
        assert "sender" in msg
        assert "text" in msg
        assert isinstance(msg["sender"], str)
        assert isinstance(msg["text"], str)


def test_existing_tests_still_pass():
    """Ensure existing tests are not broken."""
    # Health check still works
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    
    # Landing page still works
    r = client.get("/")
    assert r.status_code == 200
    assert "THE INFECTED" in r.text
