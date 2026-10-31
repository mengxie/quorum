"""HTTP adapters. Every page works as plain HTML forms; HTMX upgrades them to partial updates."""

from collections.abc import AsyncIterator
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse

from quorum.application.service import ModerationAction, SortOrder
from quorum.domain.model import DomainError, Event, ForbiddenError, InvalidInputError, NotFoundError
from quorum.web.dependencies import (
    EventDep,
    HostEventDep,
    HubDep,
    ParticipantDep,
    ServiceDep,
    is_host,
    is_htmx,
    remember_host,
)
from quorum.web.sse import change_stream
from quorum.web.templating import qr_svg, templates

router = APIRouter()
View = Literal["audience", "host"]


def _audience_url(request: Request, event: Event) -> str:
    return str(request.url_for("event_page", code=event.code))


@router.get("/", name="home")
async def home(request: Request) -> Response:
    return templates.TemplateResponse(request, "index.html", {})


@router.post("/events", name="create_event")
async def create_event(
    request: Request, service: ServiceDep, title: Annotated[str, Form()] = ""
) -> Response:
    try:
        event, host_key = await service.create_event(title)
    except InvalidInputError as error:
        context = {"create_error": error.message, "title": title}
        return templates.TemplateResponse(request, "index.html", context, status_code=400)
    remember_host(request, event)
    # Shown once on the host page, then forgotten: only its hash is stored.
    request.session["new_host_link"] = str(
        request.url_for("claim_host", code=event.code, host_key=host_key)
    )
    return RedirectResponse(request.url_for("host_page", code=event.code), status_code=303)


@router.get("/join", name="join")
async def join(request: Request, service: ServiceDep, code: str = "") -> Response:
    try:
        event = await service.get_event(code)
    except NotFoundError as error:
        context = {"join_error": str(error), "code": code}
        return templates.TemplateResponse(request, "index.html", context, status_code=404)
    return RedirectResponse(request.url_for("event_page", code=event.code), status_code=303)


@router.get("/e/{code}", name="event_page")
async def event_page(
    request: Request,
    event: EventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    sort: SortOrder = "popular",
) -> Response:
    board = await service.board(event, participant, sort=sort)
    context = {"event": event, "board": board, "sort": sort, "view": "audience"}
    return templates.TemplateResponse(request, "event.html", context)


@router.get("/e/{code}/board", name="board")
async def board(
    request: Request,
    event: EventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    sort: SortOrder = "popular",
    view: View = "audience",
) -> Response:
    hosting = view == "host" and is_host(request, event)
    current = await service.board(event, participant, sort=sort, include_hidden=hosting)
    context = {
        "event": event,
        "board": current,
        "sort": sort,
        "view": "host" if hosting else "audience",
    }
    return templates.TemplateResponse(request, "partials/board.html", context)


@router.post("/e/{code}/questions", name="ask")
async def ask(
    request: Request,
    event: EventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    text: Annotated[str, Form()] = "",
    author_name: Annotated[str, Form()] = "",
) -> Response:
    try:
        await service.ask(event, participant, text, author_name)
    except DomainError as error:
        context = {"event": event, "text": text, "author_name": author_name, "error": error}
        if is_htmx(request):  # 200, so that HTMX swaps the form with its error in
            return templates.TemplateResponse(request, "partials/ask_form.html", context)
        current = await service.board(event, participant)
        page = {**context, "board": current, "sort": "popular", "view": "audience"}
        return templates.TemplateResponse(request, "event.html", page, status_code=400)
    if is_htmx(request):
        context = {"event": event, "author_name": author_name, "sent": True}
        return templates.TemplateResponse(request, "partials/ask_form.html", context)
    return RedirectResponse(request.url_for("event_page", code=event.code), status_code=303)


@router.get("/e/{code}/similar", name="similar")
async def similar(
    request: Request,
    event: EventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    text: str = "",
) -> Response:
    matches = await service.similar(event, participant, text)
    context = {"event": event, "matches": matches, "sort": "popular", "view": "audience"}
    return templates.TemplateResponse(request, "partials/similar.html", context)


@router.post("/e/{code}/questions/{question_id}/vote", name="vote")
async def vote(
    request: Request,
    event: EventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    question_id: UUID,
    sort: Annotated[SortOrder, Form()] = "popular",
    view: Annotated[View, Form()] = "audience",
) -> Response:
    await service.toggle_vote(event, question_id, participant)
    if is_htmx(request):
        return await board(request, event, service, participant, sort, view)
    page = "host_page" if view == "host" else "event_page"
    return RedirectResponse(request.url_for(page, code=event.code), status_code=303)


@router.get("/e/{code}/host/{host_key}", name="claim_host")
async def claim_host(
    request: Request, event: EventDep, service: ServiceDep, host_key: str
) -> Response:
    if not service.is_host_key(event, host_key):
        raise ForbiddenError("That host link isn't valid for this session.")
    remember_host(request, event)
    # Redirect so the secret leaves the address bar and the browser history entry.
    return RedirectResponse(request.url_for("host_page", code=event.code), status_code=303)


@router.get("/e/{code}/host", name="host_page")
async def host_page(
    request: Request,
    event: HostEventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    sort: SortOrder = "popular",
) -> Response:
    current = await service.board(event, participant, sort=sort, include_hidden=True)
    audience_url = _audience_url(request, event)
    context = {
        "event": event,
        "board": current,
        "sort": sort,
        "view": "host",
        "audience_url": audience_url,
        "qr": qr_svg(audience_url, title=f"QR code to join {event.title}"),
        "new_host_link": request.session.pop("new_host_link", None),
    }
    return templates.TemplateResponse(request, "host.html", context)


@router.post("/e/{code}/questions/{question_id}/moderate", name="moderate")
async def moderate(
    request: Request,
    event: HostEventDep,
    service: ServiceDep,
    participant: ParticipantDep,
    question_id: UUID,
    action: Annotated[ModerationAction, Form()],
    sort: Annotated[SortOrder, Form()] = "popular",
) -> Response:
    await service.moderate(event, question_id, action)
    if is_htmx(request):
        return await board(request, event, service, participant, sort, "host")
    return RedirectResponse(request.url_for("host_page", code=event.code), status_code=303)


@router.post("/e/{code}/open", name="set_open")
async def set_open(
    request: Request,
    event: HostEventDep,
    service: ServiceDep,
    is_open: Annotated[bool, Form()],
) -> Response:
    await service.set_open(event, is_open)
    return RedirectResponse(request.url_for("host_page", code=event.code), status_code=303)


@router.get("/e/{code}/present", name="present_page")
async def present_page(
    request: Request, event: EventDep, service: ServiceDep, participant: ParticipantDep
) -> Response:
    audience_url = _audience_url(request, event)
    context = {
        "event": event,
        "board": await service.board(event, participant),
        "join_host": request.url.netloc,
        "qr": qr_svg(audience_url, title=f"QR code to join {event.title}"),
    }
    return templates.TemplateResponse(request, "present.html", context)


@router.get("/e/{code}/present/stage", name="present_stage")
async def present_stage(
    request: Request, event: EventDep, service: ServiceDep, participant: ParticipantDep
) -> Response:
    context = {"event": event, "board": await service.board(event, participant)}
    return templates.TemplateResponse(request, "partials/stage.html", context)


@router.get("/e/{code}/stream", name="stream")
async def stream(request: Request, event: EventDep, hub: HubDep) -> StreamingResponse:
    async def body() -> AsyncIterator[str]:
        with hub.subscribe(event.id) as changes:
            async for chunk in change_stream(changes, request.is_disconnected):
                yield chunk

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(body(), media_type="text/event-stream", headers=headers)


@router.get("/healthz", name="health")
async def health(request: Request) -> JSONResponse:
    try:
        await request.app.state.pool.fetchval("SELECT 1")
    except (OSError, asyncpg.PostgresError):
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
