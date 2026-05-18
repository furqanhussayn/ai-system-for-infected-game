from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class RegisterRequest(BaseModel):
    matchId: str
    botId: str
    wave: int
    alivePlayers: List[str]
    infectedPlayers: List[str]

class RegisterResponse(BaseModel):
    botId: str
    personality: str
    behaviorMode: str
    trace: Optional[str]

class DecideRequest(BaseModel):
    matchId: str
    phase: str
    wave: int
    botId: str
    infectedPlayers: List[str]
    humanPlayers: List[str]
    taskProgress: int
    nearestHuman: Optional[str]
    botRoom: Optional[str]

class DecideActionResponse(BaseModel):
    botId: str
    behaviorMode: Optional[str]
    targetRoom: Optional[str]
    targetPlayer: Optional[str]
    shouldChase: bool
    trace: Optional[str]

class DecideResponse(BaseModel):
    behaviorMode: Optional[str]
    targetPlayer: Optional[str]
    targetRoom: Optional[str]
    trace: Optional[str]

class RespondRequest(BaseModel):
    matchId: str
    botId: str
    message: str
    recentChat: List[Dict[str, Any]]
    alivePlayers: List[str]
    infectedPlayers: List[str]

class RespondResponse(BaseModel):
    botId: str
    messages: List[str]
    trace: Optional[str]

class VoteRequest(BaseModel):
    matchId: str
    botId: str
    alivePlayers: List[str]
    infectedPlayers: List[str]
    recentChat: List[Dict[str, Any]]

class VoteResponse(BaseModel):
    botId: str
    voteTarget: Optional[str]
    trace: Optional[str]

class TraceResponse(BaseModel):
    matchId: str
    count: int
    traces: List[Dict[str, Any]]
