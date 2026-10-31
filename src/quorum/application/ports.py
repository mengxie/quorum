"""What the application needs from the outside world. Infrastructure implements these."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from quorum.domain.model import Event, Question, QuestionStatus


@dataclass(frozen=True, slots=True)
class QuestionView:
    """A question as one participant sees it."""

    id: UUID
    text: str
    author_name: str | None
    status: QuestionStatus
    created_at: datetime
    votes: int
    voted: bool
    mine: bool


class DuplicateCodeError(Exception):
    """A randomly generated event code is already taken."""


class Repository(Protocol):
    async def add_event(self, event: Event) -> None: ...
    async def find_event(self, code: str) -> Event | None: ...
    async def set_event_open(self, event_id: UUID, is_open: bool) -> None: ...
    async def add_question(self, question: Question) -> None: ...
    async def find_question(self, event_id: UUID, question_id: UUID) -> Question | None: ...
    async def count_recent_questions(
        self, event_id: UUID, author_id: UUID, since: datetime
    ) -> int: ...
    async def set_question_status(self, question_id: UUID, status: QuestionStatus) -> None: ...
    async def start_answering(self, event_id: UUID, question_id: UUID) -> None: ...
    async def toggle_vote(self, question_id: UUID, participant_id: UUID) -> bool: ...
    async def list_questions(self, event_id: UUID, participant_id: UUID) -> list[QuestionView]: ...


class ChangeNotifier(Protocol):
    """Tells every live screen of an event that something changed."""

    async def publish(self, event_id: UUID) -> None: ...
