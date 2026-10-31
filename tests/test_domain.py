from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from quorum.domain.codes import ALPHABET, format_code, new_event_code, normalise_code
from quorum.domain.model import InvalidInputError, optional_text, require_text
from quorum.domain.ranking import hot_score, rank_by_heat
from quorum.domain.similarity import find_similar, terms

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def test_codes_avoid_characters_that_are_easy_to_misread() -> None:
    assert not set("0O1I") & set(ALPHABET)
    code = new_event_code()
    assert len(code) == 6
    assert set(code) <= set(ALPHABET)


@pytest.mark.parametrize("typed", ["k7p-4qz", " K7P 4QZ ", "K7P4QZ"])
def test_codes_are_forgiving_about_how_they_are_typed(typed: str) -> None:
    assert normalise_code(typed) == "K7P4QZ"
    assert format_code("K7P4QZ") == "K7P-4QZ"


@pytest.mark.parametrize("typed", ["", "K7P", "K7P4QZX", "K0P4QZ", "K7P-4Q!"])
def test_impossible_codes_are_rejected(typed: str) -> None:
    assert normalise_code(typed) is None


def test_text_is_tidied_and_bounded() -> None:
    assert (
        require_text("  How   do\nyou test? ", field="text", max_length=280) == "How do you test?"
    )
    assert optional_text("   ", field="name", max_length=40) is None
    with pytest.raises(InvalidInputError) as empty:
        require_text(" \n ", field="text", max_length=280)
    assert empty.value.field == "text"
    with pytest.raises(InvalidInputError, match="Keep it to 5 characters"):
        require_text("123456", field="text", max_length=5)


@dataclass(frozen=True)
class Item:
    name: str
    votes: int
    created_at: datetime


def test_more_votes_rank_higher_at_the_same_age() -> None:
    assert hot_score(5, timedelta(minutes=10)) > hot_score(4, timedelta(minutes=10))


def test_newer_questions_rank_higher_with_the_same_votes() -> None:
    assert hot_score(3, timedelta(minutes=1)) > hot_score(3, timedelta(minutes=30))


def test_a_fresh_question_can_overtake_an_older_one_but_not_a_runaway_favourite() -> None:
    fresh = Item("fresh", votes=3, created_at=NOW)
    older = Item("older", votes=10, created_at=NOW - timedelta(minutes=60))
    favourite = Item("favourite", votes=40, created_at=NOW - timedelta(minutes=30))
    assert [item.name for item in rank_by_heat([older, fresh, favourite], NOW)] == [
        "favourite",
        "fresh",
        "older",
    ]


def test_ties_put_the_newer_question_first() -> None:
    a = Item("a", votes=0, created_at=NOW)
    b = Item("b", votes=0, created_at=NOW)
    later = Item("later", votes=0, created_at=NOW + timedelta(seconds=1))
    assert rank_by_heat([a, later], NOW + timedelta(seconds=1))[0].name == "later"
    assert len(rank_by_heat([a, b], NOW)) == 2


def test_terms_drop_filler_words_and_stem() -> None:
    assert terms("How do you test the migrations?") == ["test", "migration"]
    assert terms("Testing, tested, tests") == ["test", "test", "test"]
    assert terms("Which libraries?") == ["library"]


def test_similar_questions_are_found_and_unrelated_ones_are_not() -> None:
    asked = [
        ("migrations", "How do you test database migrations before a release?"),
        ("coffee", "What is the team's favourite coffee place?"),
        ("flags", "Do you use feature flags for rollouts?"),
    ]
    matches = find_similar("Testing our database migrations in CI", asked)
    assert [match.key for match in matches] == ["migrations"]
    assert find_similar("Kubernetes autoscaling limits", asked) == []
    assert find_similar("how do you", asked) == []
    assert find_similar("migrations", []) == []
