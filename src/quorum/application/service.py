"""Use cases. The web layer calls these; they enforce every rule that needs data."""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from quorum.application.ports import (
    ChangeNotifier,
    DuplicateCodeError,
    QuestionView,
    Repository,
)
from quorum.domain.codes import new_event_code, normalise_code
from quorum.domain.model import (
    MAX_NAME_LENGTH,
    MAX_QUESTION_LENGTH,
    MAX_TITLE_LENGTH,
    Event,
    NotFoundError,
    Question,
    QuestionsClosedError,
    QuestionStatus,
    RateLimitedError,
    optional_text,
    require_text,
)
from quorum.domain.ranking import rank_by_heat
from quorum.domain.similarity import find_similar, terms

SortOrder = Literal["popular", "newest"]
ModerationAction = Literal["answer", "answered", "reopen", "hide", "unhide"]


@dataclass(frozen=True, slots=True)
class Board:
    answering: QuestionView | None = None
    open: list[QuestionView] = field(default_factory=list[QuestionView])
    answered: list[QuestionView] = field(default_factory=list[QuestionView])
    hidden: list[QuestionView] = field(default_factory=list[QuestionView])


def hash_host_key(host_key: str) -> str:
    """Host keys are stored hashed, like passwords: a leaked database grants no host access."""
    return hashlib.sha256(host_key.encode()).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC)


class QuorumService:
    MAX_QUESTIONS_PER_MINUTE = 3

    def __init__(
        self,
        repository: Repository,
        notifier: ChangeNotifier,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._notifier = notifier
        self._now = clock

    async def create_event(self, title: str) -> tuple[Event, str]:
        """Returns the event and its host key. The key is shown once and never stored."""
        clean_title = require_text(title, field="title", max_length=MAX_TITLE_LENGTH)
        host_key = secrets.token_urlsafe(24)
        for _ in range(5):  # codes are random, so retry the rare collision
            event = Event(
                id=uuid4(),
                code=new_event_code(),
                title=clean_title,
                host_key_hash=hash_host_key(host_key),
                is_open=True,
                created_at=self._now(),
            )
            try:
                await self._repository.add_event(event)
            except DuplicateCodeError:
                continue
            return event, host_key
        raise RuntimeError("Could not allocate a unique event code.")

    async def get_event(self, code: str) -> Event:
        normalised = normalise_code(code)
        event = await self._repository.find_event(normalised) if normalised else None
        if event is None:
            raise NotFoundError("There's no session with that code. Check it and try again.")
        return event

    @staticmethod
    def is_host_key(event: Event, host_key: str) -> bool:
        return hmac.compare_digest(event.host_key_hash, hash_host_key(host_key))

    async def ask(
        self, event: Event, participant_id: UUID, text: str, author_name: str = ""
    ) -> Question:
        if not event.is_open:
            raise QuestionsClosedError("The host has closed questions for this session.")
        clean_text = require_text(text, field="text", max_length=MAX_QUESTION_LENGTH)
        name = optional_text(author_name, field="author_name", max_length=MAX_NAME_LENGTH)
        since = self._now() - timedelta(minutes=1)
        recent = await self._repository.count_recent_questions(event.id, participant_id, since)
        if recent >= self.MAX_QUESTIONS_PER_MINUTE:
            raise RateLimitedError("You're asking quickly. Give it a minute, then try again.")

        question = Question(
            id=uuid4(),
            event_id=event.id,
            author_id=participant_id,
            author_name=name,
            text=clean_text,
            status=QuestionStatus.OPEN,
            created_at=self._now(),
        )
        await self._repository.add_question(question)
        await self._notifier.publish(event.id)
        return question

    async def toggle_vote(self, event: Event, question_id: UUID, participant_id: UUID) -> bool:
        """Votes or un-votes. Returns whether the participant now has a vote on the question."""
        question = await self._repository.find_question(event.id, question_id)
        if question is None or question.status is QuestionStatus.HIDDEN:
            raise NotFoundError("That question isn't available any more.")
        voted = await self._repository.toggle_vote(question_id, participant_id)
        await self._notifier.publish(event.id)
        return voted

    async def moderate(self, event: Event, question_id: UUID, action: ModerationAction) -> None:
        if await self._repository.find_question(event.id, question_id) is None:
            raise NotFoundError("That question doesn't exist.")
        match action:
            case "answer":
                await self._repository.start_answering(event.id, question_id)
            case "answered":
                await self._repository.set_question_status(question_id, QuestionStatus.ANSWERED)
            case "hide":
                await self._repository.set_question_status(question_id, QuestionStatus.HIDDEN)
            case "reopen" | "unhide":
                await self._repository.set_question_status(question_id, QuestionStatus.OPEN)
        await self._notifier.publish(event.id)

    async def set_open(self, event: Event, is_open: bool) -> None:
        await self._repository.set_event_open(event.id, is_open)
        await self._notifier.publish(event.id)

    async def board(
        self,
        event: Event,
        participant_id: UUID,
        *,
        sort: SortOrder = "popular",
        include_hidden: bool = False,
    ) -> Board:
        questions = await self._repository.list_questions(event.id, participant_id)
        by_status: dict[QuestionStatus, list[QuestionView]] = {
            status: [] for status in QuestionStatus
        }
        for question in questions:
            by_status[question.status].append(question)

        open_questions = by_status[QuestionStatus.OPEN]
        if sort == "popular":
            open_questions = rank_by_heat(open_questions, self._now())
        else:
            open_questions.sort(key=lambda question: question.created_at, reverse=True)
        newest_first = sorted(
            by_status[QuestionStatus.ANSWERED], key=lambda q: q.created_at, reverse=True
        )
        answering = by_status[QuestionStatus.ANSWERING]
        return Board(
            answering=answering[0] if answering else None,
            open=open_questions,
            answered=newest_first,
            hidden=by_status[QuestionStatus.HIDDEN] if include_hidden else [],
        )

    async def similar(self, event: Event, participant_id: UUID, text: str) -> list[QuestionView]:
        """Questions that look like the one being typed, so people upvote instead of repeating."""
        if len(terms(text)) < 2:
            return []
        candidates = [
            question
            for question in await self._repository.list_questions(event.id, participant_id)
            if question.status is not QuestionStatus.HIDDEN
        ]
        matches = find_similar(text, [(question, question.text) for question in candidates])
        return [match.key for match in matches]
