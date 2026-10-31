"""PostgreSQL implementation of the Repository port. Plain SQL via asyncpg."""

from datetime import datetime
from uuid import UUID

import asyncpg

from quorum.application.ports import DuplicateCodeError, QuestionView
from quorum.domain.model import Event, Question, QuestionStatus
from quorum.infrastructure.database import Pool


class PostgresRepository:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def add_event(self, event: Event) -> None:
        try:
            await self._pool.execute(
                "INSERT INTO events (id, code, title, host_key_hash, is_open, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                event.id,
                event.code,
                event.title,
                event.host_key_hash,
                event.is_open,
                event.created_at,
            )
        except asyncpg.UniqueViolationError as error:
            raise DuplicateCodeError(event.code) from error

    async def find_event(self, code: str) -> Event | None:
        row = await self._pool.fetchrow(
            "SELECT id, code, title, host_key_hash, is_open, created_at "
            "FROM events WHERE code = $1",
            code,
        )
        if row is None:
            return None
        return Event(
            id=row["id"],
            code=row["code"],
            title=row["title"],
            host_key_hash=row["host_key_hash"],
            is_open=row["is_open"],
            created_at=row["created_at"],
        )

    async def set_event_open(self, event_id: UUID, is_open: bool) -> None:
        await self._pool.execute("UPDATE events SET is_open = $2 WHERE id = $1", event_id, is_open)

    async def add_question(self, question: Question) -> None:
        await self._pool.execute(
            "INSERT INTO questions "
            "(id, event_id, author_id, author_name, text, status, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            question.id,
            question.event_id,
            question.author_id,
            question.author_name,
            question.text,
            question.status.value,
            question.created_at,
        )

    async def find_question(self, event_id: UUID, question_id: UUID) -> Question | None:
        row = await self._pool.fetchrow(
            "SELECT id, event_id, author_id, author_name, text, status, created_at "
            "FROM questions WHERE event_id = $1 AND id = $2",
            event_id,
            question_id,
        )
        if row is None:
            return None
        return Question(
            id=row["id"],
            event_id=row["event_id"],
            author_id=row["author_id"],
            author_name=row["author_name"],
            text=row["text"],
            status=QuestionStatus(row["status"]),
            created_at=row["created_at"],
        )

    async def count_recent_questions(self, event_id: UUID, author_id: UUID, since: datetime) -> int:
        count = await self._pool.fetchval(
            "SELECT count(*) FROM questions "
            "WHERE event_id = $1 AND author_id = $2 AND created_at > $3",
            event_id,
            author_id,
            since,
        )
        return int(count)

    async def set_question_status(self, question_id: UUID, status: QuestionStatus) -> None:
        await self._pool.execute(
            "UPDATE questions SET status = $2 WHERE id = $1", question_id, status.value
        )

    async def start_answering(self, event_id: UUID, question_id: UUID) -> None:
        """Moves the current question to answered and this one to answering, atomically."""
        async with self._pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "UPDATE questions SET status = 'answered' "
                "WHERE event_id = $1 AND status = 'answering' AND id <> $2",
                event_id,
                question_id,
            )
            await connection.execute(
                "UPDATE questions SET status = 'answering' WHERE id = $1", question_id
            )

    async def toggle_vote(self, question_id: UUID, participant_id: UUID) -> bool:
        """One statement: remove the vote if present, otherwise add it."""
        voted = await self._pool.fetchval(
            """
            WITH removed AS (
                DELETE FROM votes WHERE question_id = $1 AND participant_id = $2 RETURNING 1
            )
            INSERT INTO votes (question_id, participant_id)
            SELECT $1, $2 WHERE NOT EXISTS (SELECT 1 FROM removed)
            ON CONFLICT DO NOTHING
            RETURNING true
            """,
            question_id,
            participant_id,
        )
        return voted is True

    async def list_questions(self, event_id: UUID, participant_id: UUID) -> list[QuestionView]:
        rows = await self._pool.fetch(
            """
            SELECT q.id, q.text, q.author_name, q.status, q.created_at,
                   q.author_id = $2 AS mine,
                   count(v.participant_id) AS votes,
                   coalesce(bool_or(v.participant_id = $2), false) AS voted
            FROM questions q
            LEFT JOIN votes v ON v.question_id = q.id
            WHERE q.event_id = $1
            GROUP BY q.id
            """,
            event_id,
            participant_id,
        )
        return [
            QuestionView(
                id=row["id"],
                text=row["text"],
                author_name=row["author_name"],
                status=QuestionStatus(row["status"]),
                created_at=row["created_at"],
                votes=int(row["votes"]),
                voted=bool(row["voted"]),
                mine=bool(row["mine"]),
            )
            for row in rows
        ]
