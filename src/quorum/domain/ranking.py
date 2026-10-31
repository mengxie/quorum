"""Ordering questions for a live session.

Sorting by votes alone lets the first questions win forever: they collect votes simply by being
seen longest. A "hot" score lets each vote count for less as a question ages, the idea behind
Hacker News' ranking, scaled from hours to minutes for a talk.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RankingPolicy:
    gravity: float = 1.5
    unit: timedelta = timedelta(minutes=10)


DEFAULT_POLICY = RankingPolicy()


def hot_score(votes: int, age: timedelta, policy: RankingPolicy = DEFAULT_POLICY) -> float:
    elapsed = max(age, timedelta(0)) / policy.unit
    return (votes + 1) / math.pow(elapsed + 2, policy.gravity)


class Rankable(Protocol):
    @property
    def votes(self) -> int: ...

    @property
    def created_at(self) -> datetime: ...


def rank_by_heat[T: Rankable](
    items: Iterable[T], now: datetime, policy: RankingPolicy = DEFAULT_POLICY
) -> list[T]:
    """Hottest first; among equals, the newer question first."""
    return sorted(
        items,
        key=lambda item: (
            -hot_score(item.votes, now - item.created_at, policy),
            -item.created_at.timestamp(),
        ),
    )
