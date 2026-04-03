from pydantic import BaseModel, Field
from typing import Optional, List, Any, Literal
from datetime import datetime


class Source(BaseModel):
    kind: str
    id: str
    label: Optional[str] = None


class Target(BaseModel):
    kind: str
    id: str
    label: Optional[str] = None


class MessagePayload(BaseModel):
    message_id: str
    role: str
    content: List[dict]
    summary: Optional[str] = None
    message_type: Optional[Literal["instruction", "query", "challenge", "receipt", "response", "summary"]] = None


class EventEnvelope(BaseModel):
    event_id: str
    session_id: str
    thread_id: str
    event_type: str
    source: Source
    target: Optional[Target] = None
    timestamp: str
    sequence: int
    status: str
    visibility: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    artifacts: List[Any] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class CommandPayload(BaseModel):
    text: str
    mode: Literal["conference", "direct"] = "conference"
    target: Optional[Literal["sarah", "claude"]] = None
    message_type: Literal["instruction", "query", "challenge"] = "query"
    approval_required: bool = True


class ClientCommand(BaseModel):
    command: str
    session_id: str
    thread_id: str
    payload: CommandPayload


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = "matthew"
    user_label: Optional[str] = "Matthew"


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
