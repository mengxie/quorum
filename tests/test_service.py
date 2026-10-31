from uuid import uuid4

import pytest

from quorum.application.service import QuorumService
from quorum.domain.codes import format_code
from quorum.domain.model import (
    InvalidInputError,
    NotFoundError,
    QuestionsClosedError,
    RateLimitedError,
)
from quorum.infrastructure.notifications import ChangeHub
from tests.conftest import Clock

ME, YOU, THEM = uuid4(), uuid4(), uuid4()


async def test_a_session_is_found_by_any_spelling_of_its_code(service: QuorumService) -> None:
    event, host_key = await service.create_event("  Friday   all-hands ")
    assert event.title == "Friday all-hands"
    found = await service.get_event(format_code(event.code).lower())
    assert found.id == event.id
    assert service.is_host_key(found, host_key)
    assert not service.is_host_key(found, "a-guess")


@pytest.mark.parametrize("code", ["ZZZZZZ", "not a code"])
async def test_unknown_codes_are_not_found(service: QuorumService, code: str) -> None:
    with pytest.raises(NotFoundError):
        await service.get_event(code)


async def test_asking_validates_and_tells_every_screen(
    service: QuorumService, hub: ChangeHub
) -> None:
    event, _ = await service.create_event("Talk")
    with hub.subscribe(event.id) as changes:
        question = await service.ask(event, ME, "  How do you   test? ", "  Aroha ")
        assert changes.qsize() == 1
    assert (question.text, question.author_name) == ("How do you test?", "Aroha")
    with pytest.raises(InvalidInputError) as error:
        await service.ask(event, ME, "   ")
    assert error.value.field == "text"


async def test_closed_sessions_take_no_questions(service: QuorumService) -> None:
    event, _ = await service.create_event("Talk")
    await service.set_open(event, False)
    closed = await service.get_event(event.code)
    with pytest.raises(QuestionsClosedError):
        await service.ask(closed, ME, "Too late?")


async def test_rapid_asking_is_slowed_down(service: QuorumService, clock: Clock) -> None:
    event, _ = await service.create_event("Talk")
    for n in range(QuorumService.MAX_QUESTIONS_PER_MINUTE):
        await service.ask(event, ME, f"Question number {n}")
    with pytest.raises(RateLimitedError):
        await service.ask(event, ME, "One more")
    await service.ask(event, YOU, "Someone else can still ask")
    clock.advance(seconds=61)
    await service.ask(event, ME, "And again after a minute")


async def test_votes_toggle_and_count_once_per_person(service: QuorumService) -> None:
    event, _ = await service.create_event("Talk")
    question = await service.ask(event, ME, "Worth a vote?")
    assert await service.toggle_vote(event, question.id, YOU) is True
    assert await service.toggle_vote(event, question.id, THEM) is True
    assert await service.toggle_vote(event, question.id, THEM) is False

    board = await service.board(event, YOU)
    assert (board.open[0].votes, board.open[0].voted, board.open[0].mine) == (1, True, False)
    assert (await service.board(event, ME)).open[0].mine is True


async def test_answering_a_question_moves_the_previous_one_to_answered(
    service: QuorumService,
) -> None:
    event, _ = await service.create_event("Talk")
    first = await service.ask(event, ME, "First question")
    second = await service.ask(event, YOU, "Second question")
    await service.moderate(event, first.id, "answer")
    await service.moderate(event, second.id, "answer")

    board = await service.board(event, ME)
    assert board.answering is not None
    assert board.answering.id == second.id
    assert [q.id for q in board.answered] == [first.id]


async def test_hidden_questions_leave_the_room_but_not_the_host_view(
    service: QuorumService,
) -> None:
    event, _ = await service.create_event("Talk")
    question = await service.ask(event, ME, "Something off-topic")
    await service.moderate(event, question.id, "hide")

    assert (await service.board(event, YOU)).open == []
    assert len((await service.board(event, YOU, include_hidden=True)).hidden) == 1
    with pytest.raises(NotFoundError):
        await service.toggle_vote(event, question.id, YOU)
    await service.moderate(event, question.id, "unhide")
    assert len((await service.board(event, YOU)).open) == 1


async def test_popular_order_rewards_votes_but_lets_new_questions_compete(
    service: QuorumService, clock: Clock
) -> None:
    event, _ = await service.create_event("Talk")
    early = await service.ask(event, ME, "Early question")
    clock.advance(minutes=1)
    await service.ask(event, YOU, "Quiet question")
    for voter in (uuid4() for _ in range(5)):
        await service.toggle_vote(event, early.id, voter)

    popular = await service.board(event, ME, sort="popular")
    newest = await service.board(event, ME, sort="newest")
    assert [q.text for q in popular.open] == ["Early question", "Quiet question"]
    assert [q.text for q in newest.open] == ["Quiet question", "Early question"]

    clock.advance(minutes=120)
    fresh = await service.ask(event, THEM, "Fresh question")
    await service.toggle_vote(event, fresh.id, ME)
    assert (await service.board(event, ME)).open[0].text == "Fresh question"


async def test_similar_questions_are_suggested_while_typing(service: QuorumService) -> None:
    event, _ = await service.create_event("Talk")
    await service.ask(event, ME, "How do you test database migrations before a release?")
    await service.ask(event, ME, "What's the best coffee nearby?")

    suggestions = await service.similar(event, YOU, "testing database migrations")
    assert [q.text for q in suggestions] == [
        "How do you test database migrations before a release?"
    ]
    assert await service.similar(event, YOU, "how") == []
