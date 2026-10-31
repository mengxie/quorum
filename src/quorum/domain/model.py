"""Entities, rules and expected failures. Pure Python: no I/O, no framework."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_TITLE_LENGTH = 100
MAX_QUESTION_LENGTH = 280
MAX_NAME_LENGTH = 40


class QuestionStatus(StrEnum):
    OPEN = "open"
    ANSWERING = "answering"
    ANSWERED = "answered"
    HIDDEN = "hidden"


@dataclass(frozen=True, slots=True)
class Event:
    id: UUID
    code: str
    title: str
    host_key_hash: str
    is_open: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Question:
    id: UUID
    event_id: UUID
    author_id: UUID
    author_name: str | None
    text: str
    status: QuestionStatus
    created_at: datetime


class DomainError(Exception):
    """An expected failure whose message is safe to show to the person who caused it."""


class InvalidInputError(DomainError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class NotFoundError(DomainError):
    pass


class ForbiddenError(DomainError):
    pass


class QuestionsClosedError(DomainError):
    pass


class RateLimitedError(DomainError):
    pass


def require_text(value: str, *, field: str, max_length: int) -> str:
    """Collapses runs of whitespace, then insists on 1..max_length characters."""
    text = " ".join(value.split())
    if not text:
        raise InvalidInputError(field, "This can't be empty.")
    if len(text) > max_length:
        raise InvalidInputError(field, f"Keep it to {max_length} characters.")
    return text


def optional_text(value: str, *, field: str, max_length: int) -> str | None:
    return require_text(value, field=field, max_length=max_length) if value.strip() else None
