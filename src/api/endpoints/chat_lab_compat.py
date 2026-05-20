"""
Compatibility wrapper for chat_lab.generate_chat_response used in tests.
"""

from .chat_lab import _single_bot_respond, _chat_lab_state, CHAT_LAB_MATCH_ID, PLAYER_2, ALIVE_PLAYERS, INFECTED_PLAYERS
from src.models.schemas import RespondRequest
import asyncio

async def generate_chat_response(request):
    """
    Mimic the old generate_chat_response signature.
    Accepts a RespondRequest and returns a ChatLabSendResponse.
    """
    # Use the legacy single-bot logic
    messages = await _single_bot_respond(request.message, _chat_lab_state["recentChat"])
    # Build a minimal response object
    from src.api.endpoints.chat_lab import ChatLabSendResponse
    return ChatLabSendResponse(
        userMessage=request.message,
        messages=messages,
        botMessages=messages,
        delaysMs=[],
        botEvents=[],
        recentChat=_chat_lab_state["recentChat"],
        debug={}
    )