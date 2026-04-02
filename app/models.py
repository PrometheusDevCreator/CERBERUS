from pydantic import BaseModel
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
    payload: dict = {}
    artifacts: List[Any] = []
    meta: dict = {}


class ClientCommand(BaseModel):
    command: str
    session_id: str
    thread_id: str
    payload: dict


class CreateSessionRequest(BaseModel):
    user_id: Optional[str] = "matthew"
    user_label: Optional[str] = "Matthew"


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    created_at: datetime
