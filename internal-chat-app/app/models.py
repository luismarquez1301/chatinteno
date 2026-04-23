from datetime import datetime
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class OutgoingMessage(BaseModel):
    channel_id: int
    content: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    id: int
    channel_id: int
    username: str
    display_name: str
    content: str
    created_at: datetime
