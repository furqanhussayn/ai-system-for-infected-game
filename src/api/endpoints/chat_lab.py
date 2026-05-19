"""
Meeting Chat Lab - Multi-bot meeting simulation endpoint.

Simulates a chaotic meeting with:
- player_1: human user
- player_2: deflector / defensive AI bot
- player_3: accuser / instigator AI bot
- player_4: confused / quiet AI bot

Uses in-memory state for chat history and tracking.
"""

from __future__ import annotations

import json
import random
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.agents.chat_style_guard import clean_message, is_bad_bot_output, sanitize_messages
from src.agents.meeting_chat_prompt import build_meeting_chat_prompt
from src.agents.meeting_orchestrator import (
    BotParticipant,
    ResponderPlan,
    calculate_event_delay,
    classify_latest_message as classify_multi,
    detect_targeted_player,
    generate_human_fallback,
    select_responders,
)
from src.agents.trace_logger import add_trace
from src.core import config
from src.models.schemas import RespondRequest
from src.services.llm_adapter import generate_chat_response
from src.api.endpoints.respond import build_response_payload as original_build_response_payload

router = APIRouter()

# Fixed Chat Lab IDs
CHAT_LAB_MATCH_ID = "CHAT_LAB"
PLAYER_1 = "player_1"
PLAYER_2 = "player_2"
PLAYER_3 = "player_3"
PLAYER_4 = "player_4"
ALIVE_PLAYERS = [PLAYER_1, PLAYER_2, PLAYER_3, PLAYER_4]
INFECTED_PLAYERS = [PLAYER_2]

# Default bot participants
BOT_PARTICIPANTS = [
    BotParticipant(PLAYER_2, "deflector", 0.6, 0.4, 0.2, 0.8),
    BotParticipant(PLAYER_3, "accuser", 0.55, 0.7, 0.1, 0.2),
    BotParticipant(PLAYER_4, "confused", 0.35, 0.2, 0.8, 0.3),
]

# In-memory chat lab state
_chat_lab_state: dict[str, Any] = {
    "recentChat": [],
    "accusationsCount": {},
    "accusedBy": {},
    "lastBotSpeaker": None,
    "lastTargetedPlayer": None,
    "lastMessageClassification": None,
    "repeatedAccusations": 0,
}


class ChatLabSendRequest(BaseModel):
    message: str
    forceResponse: bool = True
    debug: bool = True
    multiBot: bool = True


class BotEvent(BaseModel):
    sender: str
    text: str
    delayMs: int


class ChatLabSendResponse(BaseModel):
    userMessage: str
    messages: list[str] = []          # legacy flat list
    botMessages: list[str] = []       # legacy flat list
    delaysMs: list[int] = []          # legacy flat list
    botEvents: list[dict[str, Any]] = []
    recentChat: list[dict[str, str]]
    debug: dict[str, Any] = {}


class ChatLabResetResponse(BaseModel):
    status: str
    matchId: str


# ---------------------------------------------------------------------------
# HTML Frontend
# ---------------------------------------------------------------------------

@router.get("/chat_lab", response_class=HTMLResponse)
async def get_chat_lab():
    """Return Meeting Chat Lab HTML interface with multi-bot UI."""
    ai_mode = config.AI_MODE
    llm_provider = config.LLM_PROVIDER
    status_text = f"{ai_mode.upper()} mode • {llm_provider.upper()}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>THE INFECTED — Meeting Chat Lab</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}

        .header {{
            text-align: center;
            margin-bottom: 20px;
        }}

        .header h1 {{
            font-size: 28px;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #ff006e, #fb5607);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: 2px;
        }}

        .status-badge {{
            display: inline-block;
            padding: 6px 12px;
            background: rgba(255, 100, 100, 0.2);
            border: 1px solid #ff6464;
            border-radius: 20px;
            font-size: 12px;
            color: #ff8888;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 8px;
        }}

        .participants {{
            display: flex;
            justify-content: center;
            gap: 16px;
            margin: 12px 0;
            flex-wrap: wrap;
        }}

        .participant {{
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: bold;
        }}

        .participant.you {{
            background: rgba(74, 144, 226, 0.25);
            border: 1px solid #4a90e2;
            color: #4a90e2;
        }}

        .participant.p2 {{
            background: rgba(255, 100, 100, 0.25);
            border: 1px solid #ff6464;
            color: #ff6464;
        }}

        .participant.p3 {{
            background: rgba(245, 166, 35, 0.25);
            border: 1px solid #f5a623;
            color: #f5a623;
        }}

        .participant.p4 {{
            background: rgba(0, 255, 156, 0.25);
            border: 1px solid #00ff9c;
            color: #00ff9c;
        }}

        .explanation {{
            background: rgba(100, 150, 200, 0.1);
            border-left: 3px solid #4a90e2;
            padding: 12px 16px;
            border-radius: 4px;
            margin-bottom: 16px;
            font-size: 14px;
            line-height: 1.6;
        }}

        .lab-container {{
            background: rgba(20, 20, 40, 0.8);
            border: 1px solid rgba(255, 100, 150, 0.3);
            border-radius: 8px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }}

        .chat-history {{
            background: rgba(10, 10, 25, 0.8);
            border: 1px solid rgba(100, 150, 200, 0.2);
            border-radius: 6px;
            padding: 16px;
            height: 420px;
            overflow-y: auto;
            margin-bottom: 12px;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .message {{
            margin-bottom: 6px;
            display: flex;
            gap: 8px;
            padding: 6px 8px;
            border-radius: 4px;
            animation: fadeIn 0.3s ease;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(4px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .message.player1 {{
            justify-content: flex-end;
            background: rgba(74, 144, 226, 0.08);
        }}

        .message.player2 {{
            justify-content: flex-start;
            background: rgba(255, 100, 100, 0.08);
        }}

        .message.player3 {{
            justify-content: flex-start;
            background: rgba(245, 166, 35, 0.08);
        }}

        .message.player4 {{
            justify-content: flex-start;
            background: rgba(0, 255, 156, 0.08);
        }}

        .message-sender {{
            font-size: 11px;
            font-weight: bold;
            color: #888;
            min-width: 60px;
        }}

        .message.player1 .message-sender {{
            text-align: right;
            color: #4a90e2;
        }}
        .message.player2 .message-sender {{
            text-align: left;
            color: #ff6464;
        }}
        .message.player3 .message-sender {{
            text-align: left;
            color: #f5a623;
        }}
        .message.player4 .message-sender {{
            text-align: left;
            color: #00ff9c;
        }}

        .message-text {{
            flex: 1;
            word-wrap: break-word;
            color: #e0e0e0;
            font-size: 14px;
            line-height: 1.4;
        }}

        .typing-indicator {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 8px;
            border-radius: 4px;
            margin-bottom: 4px;
        }}

        .typing-indicator.p2 {{ background: rgba(255, 100, 100, 0.06); }}
        .typing-indicator.p3 {{ background: rgba(245, 166, 35, 0.06); }}
        .typing-indicator.p4 {{ background: rgba(0, 255, 156, 0.06); }}

        .typing-sender {{
            font-size: 12px;
            font-weight: bold;
        }}
        .typing-indicator.p2 .typing-sender {{ color: #ff6464; }}
        .typing-indicator.p3 .typing-sender {{ color: #f5a623; }}
        .typing-indicator.p4 .typing-sender {{ color: #00ff9c; }}

        .typing-dots {{
            display: flex;
            gap: 4px;
            align-items: center;
        }}

        .typing-dots span {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            opacity: 0.4;
            animation: typingBounce 1.2s infinite ease-in-out;
        }}
        .typing-indicator.p2 .typing-dots span {{ background: #ff6464; }}
        .typing-indicator.p3 .typing-dots span {{ background: #f5a623; }}
        .typing-indicator.p4 .typing-dots span {{ background: #00ff9c; }}

        .typing-dots span:nth-child(1) {{ animation-delay: 0s; }}
        .typing-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
        .typing-dots span:nth-child(3) {{ animation-delay: 0.4s; }}

        @keyframes typingBounce {{
            0%, 60%, 100% {{ opacity: 0.4; transform: translateY(0); }}
            30% {{ opacity: 1; transform: translateY(-4px); }}
        }}

        .silence-msg {{
            text-align: center;
            font-size: 12px;
            color: #666;
            padding: 8px;
            font-style: italic;
            animation: fadeIn 0.3s ease;
        }}

        .controls {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            margin-bottom: 10px;
        }}

        .input-area {{
            display: flex;
            gap: 8px;
            flex: 1;
            min-width: 200px;
        }}

        .input-area input {{
            flex: 1;
            padding: 10px 12px;
            background: rgba(40, 60, 100, 0.5);
            border: 1px solid rgba(100, 150, 200, 0.3);
            border-radius: 4px;
            color: #e0e0e0;
            font-size: 14px;
        }}

        .input-area input::placeholder {{ color: #666; }}
        .input-area input:focus {{
            outline: none;
            border-color: #4a90e2;
            background: rgba(40, 60, 100, 0.7);
        }}

        .button {{
            padding: 10px 16px;
            border: none;
            border-radius: 4px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .button-send {{
            background: linear-gradient(135deg, #ff006e, #fb5607);
            color: white;
        }}
        .button-send:hover:not(:disabled) {{
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(255, 0, 110, 0.4);
        }}
        .button-send:disabled {{ opacity: 0.5; cursor: not-allowed; transform: none; }}

        .button-reset {{
            background: rgba(100, 100, 100, 0.4);
            color: #aaa;
            border: 1px solid rgba(150, 150, 150, 0.3);
        }}
        .button-reset:hover {{ background: rgba(120, 120, 120, 0.5); color: #ddd; }}

        .checkbox-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            font-size: 13px;
            color: #aaa;
        }}

        .checkbox-group label {{
            display: flex;
            align-items: center;
            gap: 4px;
            cursor: pointer;
        }}

        .checkbox-group input[type="checkbox"] {{
            accent-color: #ff6464;
        }}

        .status-line {{
            text-align: center;
            font-size: 12px;
            color: #666;
            margin-top: 10px;
        }}

        .error {{
            color: #ff6464;
            font-size: 12px;
            padding: 8px;
            background: rgba(255, 100, 100, 0.1);
            border-radius: 4px;
            margin-bottom: 10px;
            display: none;
        }}
        .error.show {{ display: block; }}

        .loading {{ color: #4a90e2; font-size: 12px; padding: 4px 0; display: none; }}
        .loading.show {{ display: block; }}

        .debug-panel {{
            background: rgba(10, 10, 25, 0.9);
            border: 1px solid rgba(100, 150, 200, 0.2);
            border-radius: 6px;
            padding: 12px;
            margin-top: 12px;
            font-family: monospace;
            font-size: 12px;
            color: #aaa;
            display: none;
            white-space: pre-wrap;
        }}
        .debug-panel.show {{ display: block; }}
        .debug-panel .debug-label {{ color: #4a90e2; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎭 THE INFECTED</h1>
            <div>Meeting Chat Lab — Multi-Bot</div>
            <div class="status-badge">{status_text}</div>
            <div class="participants">
                <span class="participant you">player_1: you</span>
                <span class="participant p2">player_2</span>
                <span class="participant p3">player_3</span>
                <span class="participant p4">player_4</span>
            </div>
        </div>

        <div class="explanation">
            <strong>Chaotic Meeting Simulation</strong><br>
            <strong>player_1</strong> = you &nbsp;|&nbsp;
            <strong>player_2</strong> = deflector &nbsp;|&nbsp;
            <strong>player_3</strong> = accuser &nbsp;|&nbsp;
            <strong>player_4</strong> = confused<br>
            Type accusations, questions, or random chat. Bots respond with realistic typing delays.
            Hidden role: player_2 is infected (never revealed).
        </div>

        <div class="lab-container">
            <div class="error" id="error-msg"></div>
            <div class="loading" id="loading-msg">● meeting thinking...</div>

            <div class="chat-history" id="chat-history">
                <div style="color: #666; font-size: 12px; margin: auto;">
                    Chat history appears here. Send a message to start.
                </div>
            </div>

            <div class="controls">
                <div class="input-area">
                    <input
                        type="text"
                        id="message-input"
                        placeholder="Try: player 2 is sus / vote player 2 / who is sus / u sound like a bot"
                        autocomplete="off"
                    />
                    <button class="button button-send" id="send-btn">Send</button>
                    <button class="button button-reset" id="reset-btn">Reset</button>
                </div>
            </div>

            <div class="checkbox-group">
                <label><input type="checkbox" id="force-check" checked> Force at least one bot response</label>
                <label><input type="checkbox" id="debug-check" checked> Show debug info</label>
                <label><input type="checkbox" id="multibot-check" checked> Multi Bot Mode</label>
            </div>

            <div class="status-line" id="status-line"></div>
            <div class="debug-panel" id="debug-panel"></div>
        </div>
    </div>

    <script>
        const CHAT_HISTORY = document.getElementById('chat-history');
        const MESSAGE_INPUT = document.getElementById('message-input');
        const SEND_BTN = document.getElementById('send-btn');
        const RESET_BTN = document.getElementById('reset-btn');
        const ERROR_MSG = document.getElementById('error-msg');
        const LOADING_MSG = document.getElementById('loading-msg');
        const STATUS_LINE = document.getElementById('status-line');
        const DEBUG_PANEL = document.getElementById('debug-panel');
        const FORCE_CHECK = document.getElementById('force-check');
        const DEBUG_CHECK = document.getElementById('debug-check');
        const MULTIBOT_CHECK = document.getElementById('multibot-check');

        let chatHistoryData = [];

        function sleep(ms) {{
            return new Promise(resolve => setTimeout(resolve, ms));
        }}

        function showError(msg) {{
            ERROR_MSG.textContent = '⚠ ' + msg;
            ERROR_MSG.classList.add('show');
            setTimeout(() => ERROR_MSG.classList.remove('show'), 5000);
        }}

        function showLoading(show) {{
            if (show) {{
                LOADING_MSG.classList.add('show');
                SEND_BTN.disabled = true;
            }} else {{
                LOADING_MSG.classList.remove('show');
                SEND_BTN.disabled = false;
            }}
        }}

        function escapeHtml(text) {{
            const d = document.createElement('div');
            d.textContent = text;
            return d.innerHTML;
        }}

        function appendMessage(sender, text) {{
            // Remove placeholder
            const ph = CHAT_HISTORY.querySelector('[data-placeholder]');
            if (ph) ph.remove();

            let cls = 'message';
            if (sender === 'player_1') cls += ' player1';
            else if (sender === 'player_2') cls += ' player2';
            else if (sender === 'player_3') cls += ' player3';
            else if (sender === 'player_4') cls += ' player4';

            const div = document.createElement('div');
            div.className = cls;
            div.innerHTML = `
                <div class="message-sender">${{escapeHtml(sender)}}</div>
                <div class="message-text">${{escapeHtml(text)}}</div>
            `;
            CHAT_HISTORY.appendChild(div);
            CHAT_HISTORY.scrollTop = CHAT_HISTORY.scrollHeight;
        }}

        function showSilenceMsg() {{
            const div = document.createElement('div');
            div.className = 'silence-msg';
            div.id = 'silence-msg';
            div.textContent = '[no bot response — silence triggered]';
            CHAT_HISTORY.appendChild(div);
            CHAT_HISTORY.scrollTop = CHAT_HISTORY.scrollHeight;
        }}

        function removeSilenceMsg() {{
            const el = document.getElementById('silence-msg');
            if (el) el.remove();
        }}

        function showTyping(sender) {{
            removeTyping(sender);
            const div = document.createElement('div');
            div.className = 'typing-indicator';
            let cls = 'typing-indicator';
            if (sender === 'player_2') cls += ' p2';
            else if (sender === 'player_3') cls += ' p3';
            else if (sender === 'player_4') cls += ' p4';
            div.className = cls;
            div.id = 'typing-' + sender;
            div.style.marginBottom = '4px';
            div.innerHTML = `
                <span class="typing-sender">${{escapeHtml(sender)}} is typing...</span>
                <div class="typing-dots"><span></span><span></span><span></span></div>
            `;
            CHAT_HISTORY.appendChild(div);
            CHAT_HISTORY.scrollTop = CHAT_HISTORY.scrollHeight;
            return div;
        }}

        function removeTyping(sender) {{
            const el = document.getElementById('typing-' + sender);
            if (el) el.remove();
        }}

        function updateDebug(debugInfo) {{
            if (!debugInfo || !DEBUG_CHECK.checked) {{
                DEBUG_PANEL.classList.remove('show');
                return;
            }}
            const lines = [];
            if (debugInfo.classification) lines.push('classification: ' + debugInfo.classification);
            if (debugInfo.targetedPlayer) lines.push('targetedPlayer: ' + debugInfo.targetedPlayer);
            if (debugInfo.selectedResponders && debugInfo.selectedResponders.length)
                lines.push('selectedResponders: [' + debugInfo.selectedResponders.join(', ') + ']');
            if (debugInfo.forcedResponder) lines.push('forcedResponder: ' + debugInfo.forcedResponder);
            if (debugInfo.silenceReason) lines.push('silenceReason: ' + debugInfo.silenceReason);
            if (debugInfo.aiMode) lines.push('aiMode: ' + debugInfo.aiMode);
            if (debugInfo.llmUsed !== undefined) lines.push('llmUsed: ' + debugInfo.llmUsed);
            if (debugInfo.fallbackUsed !== undefined) lines.push('fallbackUsed: ' + debugInfo.fallbackUsed);
            if (debugInfo.selectionReasons && debugInfo.selectionReasons.length)
                lines.push('reasons:\\n  ' + debugInfo.selectionReasons.join('\\n  '));
            DEBUG_PANEL.innerHTML = '<div class="debug-label">🔍 Debug Info</div>' + escapeHtml(lines.join('\\n'));
            DEBUG_PANEL.classList.add('show');
        }}

        async function sendMessage() {{
            const msg = MESSAGE_INPUT.value.trim();
            if (!msg) return;

            showLoading(true);
            removeSilenceMsg();
            ERROR_MSG.classList.remove('show');
            MESSAGE_INPUT.value = '';

            appendMessage('player_1', msg);

            try {{
                const response = await fetch('/chat_lab/send', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        message: msg,
                        forceResponse: FORCE_CHECK.checked,
                        debug: DEBUG_CHECK.checked,
                        multiBot: MULTIBOT_CHECK.checked
                    }})
                }});

                if (!response.ok) {{
                    const err = await response.json();
                    throw new Error(err.detail || 'Backend error');
                }}

                const data = await response.json();
                chatHistoryData = data.recentChat || [];

                // Debug panel
                if (data.debug) {{
                    updateDebug(data.debug);
                }}

                // Bot events
                const events = data.botEvents || [];
                const flatMsgs = data.messages || data.botMessages || [];
                const flatDelays = data.delaysMs || [];

                if (events.length > 0) {{
                    for (const evt of events) {{
                        showTyping(evt.sender);
                        await sleep(evt.delayMs);
                        removeTyping(evt.sender);
                        appendMessage(evt.sender, evt.text);
                    }}
                }} else if (flatMsgs.length > 0) {{
                    for (let i = 0; i < flatMsgs.length; i++) {{
                        const delay = flatDelays[i] || 1800;
                        showTyping('player_2');
                        await sleep(delay);
                        removeTyping('player_2');
                        appendMessage('player_2', flatMsgs[i]);
                    }}
                }} else {{
                    // Silence
                    showSilenceMsg();
                }}

                updateStatusLine();

            }} catch (err) {{
                showLoading(false);
                showError(err.message || 'Network error');
                MESSAGE_INPUT.focus();
            }}

            showLoading(false);
            MESSAGE_INPUT.focus();
        }}

        function updateStatusLine() {{
            const count = CHAT_HISTORY.querySelectorAll('.message').length;
            STATUS_LINE.textContent = count > 0 ? 'Messages: ' + count : '';
        }}

        async function resetChat() {{
            if (!confirm('Clear all messages?')) return;

            showLoading(true);
            try {{
                const response = await fetch('/chat_lab/reset', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}}
                }});
                if (!response.ok) throw new Error('Reset failed');

                chatHistoryData = [];
                CHAT_HISTORY.innerHTML = '<div style="color: #666; font-size: 12px; margin: auto;" data-placeholder>Chat history appears here. Send a message to start.</div>';
                ERROR_MSG.classList.remove('show');
                DEBUG_PANEL.classList.remove('show');
                STATUS_LINE.textContent = '';

            }} catch (err) {{
                showError(err.message || 'Reset failed');
            }} finally {{
                showLoading(false);
                MESSAGE_INPUT.focus();
            }}
        }}

        SEND_BTN.addEventListener('click', sendMessage);
        RESET_BTN.addEventListener('click', resetChat);
        MESSAGE_INPUT.addEventListener('keydown', (e) => {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }});

        MESSAGE_INPUT.focus();
    </script>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Multi-bot chat send
# ---------------------------------------------------------------------------

async def _llm_for_bot(
    bot_id: str,
    message: str,
    recent_chat: list,
    intent: str,
    targeted_player: str | None,
    is_targeted: bool,
) -> list[str]:
    """
    Try to generate chat using LLM (Groq).
    Returns list of messages or empty list if LLM fails/shouldn't be used.
    """
    if config.AI_MODE not in ("groq", "agent"):
        return []

    if not config.GROQ_API_KEY.strip() and config.AI_MODE == "groq":
        return []

    try:
        fake_req = RespondRequest(
            matchId=CHAT_LAB_MATCH_ID,
            botId=bot_id,
            message=message,
            recentChat=recent_chat,
            alivePlayers=ALIVE_PLAYERS,
            infectedPlayers=INFECTED_PLAYERS,
        )
        prompt = build_meeting_chat_prompt(
            fake_req,
            intent=intent,
            targeted_player=targeted_player,
            is_targeted=is_targeted,
        )
        llm_text = await generate_chat_response(prompt)
        if isinstance(llm_text, str) and llm_text.strip():
            raw_parts = [p.strip() for p in llm_text.split("|") if p.strip()]
            cleaned = sanitize_messages(raw_parts[:5])
            if cleaned:
                return cleaned
    except Exception:
        pass

    return []


async def _single_bot_respond(
    message: str,
    recent_chat: list,
) -> list[str]:
    """
    Legacy single-bot response for backwards compat.
    Uses existing respond pipeline for player_2 only.
    """
    try:
        fake_req = RespondRequest(
            matchId=CHAT_LAB_MATCH_ID,
            botId=PLAYER_2,
            message=message,
            recentChat=recent_chat,
            alivePlayers=ALIVE_PLAYERS,
            infectedPlayers=INFECTED_PLAYERS,
        )
        messages, _, _, _ = await original_build_response_payload(fake_req, use_llm=True)
        return messages
    except Exception:
        return []


# State tracking helpers

def _update_state(targeted_player: str | None, classification: str):
    state = _chat_lab_state
    if targeted_player:
        if targeted_player == state["lastTargetedPlayer"]:
            state["repeatedAccusations"] += 1
        else:
            state["repeatedAccusations"] = 0
        state["lastTargetedPlayer"] = targeted_player
    state["lastMessageClassification"] = classification


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat_lab/send")
async def send_chat_lab_message(req: ChatLabSendRequest):
    """
    Send a message in the chat lab.

    Supports multi-bot response with botEvents[].delayMs.
    Falls back to legacy single-bot format for backwards compat.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_message = req.message.strip()
    state = _chat_lab_state

    # Add user message to chat
    state["recentChat"].append({
        "sender": PLAYER_1,
        "text": user_message,
    })

    try:
        targeted_player = detect_targeted_player(user_message)
        classification = classify_multi(user_message, "", targeted_player)
        _update_state(targeted_player, classification)

        if req.multiBot:
            # Multi-bot mode
            plans, debug_info = select_responders(
                user_message,
                recent_chat=state["recentChat"],
                force_response=req.forceResponse,
                debug=req.debug,
            )

            bot_events = []
            all_texts = []
            all_delays = []

            for plan in plans:
                bot_id = plan.botId
                is_target = plan.isDirectTarget or (targeted_player == bot_id)
                target_player_for_prompt = targeted_player

                # Try LLM first
                llm_messages = await _llm_for_bot(
                    bot_id,
                    user_message,
                    state["recentChat"],
                    plan.intent,
                    target_player_for_prompt,
                    is_target,
                )

                if llm_messages:
                    use_messages = llm_messages
                    debug_info["llmUsed"] = True
                else:
                    # Fallback
                    use_messages = generate_human_fallback(
                        user_message,
                        bot_id,
                        state["recentChat"],
                        personality=None,
                        intent=plan.intent,
                        targeted_player=target_player_for_prompt,
                    )
                    debug_info["fallbackUsed"] = True

                # Clean messages
                cleaned = []
                for m in use_messages:
                    cm = clean_message(m)
                    if cm and not is_bad_bot_output(cm):
                        cleaned.append(cm)

                if not cleaned:
                    continue

                # Add to state
                for msg in cleaned:
                    state["recentChat"].append({
                        "sender": bot_id,
                        "text": msg,
                    })

                # Build events with delays
                for idx, msg_text in enumerate(cleaned):
                    delay = calculate_event_delay(
                        bot_id, msg_text, classification, plan.intent,
                        is_target, idx,
                    )
                    bot_events.append({
                        "sender": bot_id,
                        "text": msg_text,
                        "delayMs": delay,
                    })
                    all_texts.append(msg_text)
                    all_delays.append(delay)

                state["lastBotSpeaker"] = bot_id

            # Build debug info
            debug_out = {
                "classification": debug_info.get("classification", classification),
                "targetedPlayer": targeted_player,
                "selectedResponders": debug_info.get("selectedResponders", []),
                "forcedResponder": debug_info.get("forcedResponder"),
                "silenceReason": debug_info.get("silenceReason"),
                "aiMode": config.AI_MODE,
                "llmUsed": debug_info.get("llmUsed", False),
                "fallbackUsed": debug_info.get("fallbackUsed", False),
                "selectionReasons": debug_info.get("selectionReasons", []),
            }

            if not req.debug:
                debug_out = {}

            return {
                "userMessage": user_message,
                "messages": all_texts,
                "botMessages": all_texts,
                "delaysMs": all_delays,
                "botEvents": bot_events,
                "recentChat": state["recentChat"],
                "debug": debug_out,
            }

        else:
            # Legacy single-bot mode
            messages = await _single_bot_respond(user_message, state["recentChat"])

            # Add bot messages to chat
            for bot_msg in messages:
                state["recentChat"].append({
                    "sender": PLAYER_2,
                    "text": bot_msg,
                })

            # Compute delays
            from src.agents.chat_delays import calculate_message_delays
            delays_ms = calculate_message_delays(messages, classification)

            bot_events = []
            for i, msg in enumerate(messages):
                bot_events.append({
                    "sender": PLAYER_2,
                    "text": msg,
                    "delayMs": delays_ms[i] if i < len(delays_ms) else 1500,
                })

            return ChatLabSendResponse(
                userMessage=user_message,
                messages=messages,
                botMessages=messages,
                delaysMs=delays_ms,
                botEvents=bot_events,
                recentChat=state["recentChat"],
                debug={
                    "classification": classification,
                    "targetedPlayer": targeted_player,
                    "silenceReason": None if messages else "no response generated",
                    "aiMode": config.AI_MODE,
                    "llmUsed": False,
                    "fallbackUsed": True,
                } if req.debug else {},
            )

    except Exception as e:
        # Remove the user message we added if anything failed
        if state["recentChat"] and state["recentChat"][-1]["sender"] == PLAYER_1:
            state["recentChat"].pop()
        raise HTTPException(status_code=500, detail=f"Respond error: {str(e)}")


@router.post("/chat_lab/reset", response_model=ChatLabResetResponse)
async def reset_chat_lab():
    """Clear the chat lab history and reset state."""
    _chat_lab_state["recentChat"] = []
    _chat_lab_state["accusationsCount"] = {}
    _chat_lab_state["accusedBy"] = {}
    _chat_lab_state["lastBotSpeaker"] = None
    _chat_lab_state["lastTargetedPlayer"] = None
    _chat_lab_state["lastMessageClassification"] = None
    _chat_lab_state["repeatedAccusations"] = 0
    return ChatLabResetResponse(
        status="reset",
        matchId=CHAT_LAB_MATCH_ID,
    )