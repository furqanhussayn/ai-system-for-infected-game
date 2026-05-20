from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ChatMessageDto(ApiModel):
    sender: str
    senderName: Optional[str] = None
    text: str


class RegisterBotRequest(ApiModel):
    matchId: str
    botId: str
    botName: str = ""
    wave: int = 0
    cycle: int = 0
    phase: str = "Lobby"
    alivePlayers: list[str] = Field(default_factory=list)
    humanPlayers: list[str] = Field(default_factory=list)
    infectedPlayers: list[str] = Field(default_factory=list)
    taskProgress: int = 0


class RegisterBotResponse(ApiModel):
    ok: bool = True
    botId: str
    personality: str
    behaviorMode: str
    trace: Optional[str] = None


class UnregisterBotRequest(ApiModel):
    matchId: str
    botId: str
    reason: Optional[str] = None


class UnregisterBotResponse(ApiModel):
    ok: bool = True
    botId: str
    trace: Optional[str] = None


class DecideActionRequest(ApiModel):
    matchId: str
    phase: str = "Lobby"
    wave: int = 0
    cycle: int = 0
    botId: str
    botName: str = ""
    infectedPlayers: list[str] = Field(default_factory=list)
    humanPlayers: list[str] = Field(default_factory=list)
    alivePlayers: list[str] = Field(default_factory=list)
    taskProgress: int = 0
    nearestHuman: Optional[str] = None
    botRoom: Optional[str] = None
    nearestHumanRoom: Optional[str] = None
    secondsSinceLastSeenHuman: Optional[float] = None
    isFinalChase: bool = False


class DecideActionResponse(ApiModel):
    botId: str
    behaviorMode: str
    targetRoom: Optional[str] = None
    targetPlayer: Optional[str] = None
    shouldChase: bool = False
    nextDecisionInSeconds: int = 20
    trace: Optional[str] = None


class RespondRequest(ApiModel):
    matchId: str
    phase: str = "Meeting"
    wave: int = 0
    cycle: int = 0
    botId: str
    botName: str = ""
    personality: Optional[str] = None
    # Optional language hint for generated chat output. Examples: 'en', 'roman_urdu'
    language: Optional[str] = "en"
    message: str = ""
    latestMessage: Optional[ChatMessageDto] = None
    recentChat: list[ChatMessageDto] = Field(default_factory=list)
    alivePlayers: list[str] = Field(default_factory=list)
    humanPlayers: list[str] = Field(default_factory=list)
    infectedPlayers: list[str] = Field(default_factory=list)
    simulateDelay: bool = False


class RespondResponse(ApiModel):
    botId: str
    respond: bool = False
    messages: list[str] = Field(default_factory=list)
    typingDelaySeconds: float = 0.0
    secondMessageDelaySeconds: float = 0.0
    trace: Optional[str] = None
    delaysMs: list[int] = Field(default_factory=list)


class VoteRequest(ApiModel):
    matchId: str
    phase: str = "Lobby"
    wave: int = 0
    cycle: int = 0
    botId: str
    botName: str = ""
    alivePlayers: list[str] = Field(default_factory=list)
    humanPlayers: list[str] = Field(default_factory=list)
    infectedPlayers: list[str] = Field(default_factory=list)
    recentChat: list[ChatMessageDto] = Field(default_factory=list)


class VoteResponse(ApiModel):
    botId: str
    voteTarget: Optional[str] = None
    reason: Optional[str] = None
    trace: Optional[str] = None


class TraceEntry(ApiModel):
    ts: str
    timestamp: Optional[str] = None
    action: Optional[str] = None
    eventType: str
    matchId: str
    botId: str
    input: str = ""
    output: str = ""
    trace: str = ""
    source: Optional[str] = None


class TraceResponse(ApiModel):
    matchId: str
    count: int
    traces: list[TraceEntry] = Field(default_factory=list)


RegisterRequest = RegisterBotRequest
RegisterResponse = RegisterBotResponse
DecideRequest = DecideActionRequest
DecideResponse = DecideActionResponse
