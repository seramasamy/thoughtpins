"""Chat and question-answering request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AskResponse(BaseModel):
    query: str
    answer: str
    context_size_chars: int = 0


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)
    conversation_id: str = Field(default="default", max_length=128)
    surface: str = Field(default="web", max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    message_id: str = Field(default="", max_length=128)
    include_private: bool | None = Field(
        default=None,
        title="Use private memories",
        description=(
            "Allow memories already marked private to inform this response. "
            "Private memories stay out of recall when this is false."
        ),
    )
    confirm_action: bool = False
    pending_action_id: str | None = Field(default=None, max_length=32)
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": "hey, what should I remember from last week?", "conversation_id": "main"},
                {"text": "today I met Maya at Koyo and we talked about the launch", "conversation_id": "main"},
                {"text": "that was just chat", "conversation_id": "main"},
            ]
        }
    }

    @field_validator("text")
    @classmethod
    def strip_chat_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be empty")
        return value

    @field_validator("conversation_id", "surface", "message_id")
    @classmethod
    def strip_chat_metadata(cls, value: str) -> str:
        return value.strip()


class ChatConversationResponse(BaseModel):
    id: str
    conversation_key: str
    surface: str
    title: str | None = None
    created_at_utc: str | None = None
    updated_at_utc: str | None = None
    last_message_at_utc: str | None = None


class ChatConversationsPageResponse(BaseModel):
    items: list[ChatConversationResponse]
    page: int
    limit: int
    total: int
    has_next: bool
    next_cursor: str | None = None


class ChatMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    text: str
    route_type: str | None = None
    status: str | None = None
    entry_id: str | None = None
    job_id: str | None = None
    document_id: str | None = None
    created_at_utc: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessagesPageResponse(BaseModel):
    items: list[ChatMessageResponse]
    page: int
    limit: int
    total: int
    has_next: bool
    next_cursor: str | None = None


class ChatResponse(BaseModel):
    status: str
    route_type: str
    reply: str
    entry_id: str | None = None
    job_id: str | None = None
    document_id: str | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    context_size_chars: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "replied",
                    "route_type": "chat",
                    "reply": "I remember that. Last week your journal focused on...",
                    "requires_confirmation": False,
                },
                {
                    "status": "ok",
                    "route_type": "journal_entry",
                    "reply": "Saved. Captured: 2 memories, 1 entity.",
                    "entry_id": "entry_abc123",
                },
            ]
        }
    }
