from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import Depends, Request

from quorum.application.service import QuorumService
from quorum.domain.model import Event, ForbiddenError
from quorum.infrastructure.notifications import ChangeHub


def get_service(request: Request) -> QuorumService:
    return cast(QuorumService, request.app.state.service)


def get_hub(request: Request) -> ChangeHub:
    return cast(ChangeHub, request.app.state.hub)


ServiceDep = Annotated[QuorumService, Depends(get_service)]
HubDep = Annotated[ChangeHub, Depends(get_hub)]


async def get_event(code: str, service: ServiceDep) -> Event:
    return await service.get_event(code)


EventDep = Annotated[Event, Depends(get_event)]


def get_participant(request: Request) -> UUID:
    """An anonymous, per-browser id kept in the signed session cookie: one vote per person."""
    raw = request.session.get("participant")
    if isinstance(raw, str):
        try:
            return UUID(raw)
        except ValueError:
            pass
    participant = uuid4()
    request.session["participant"] = str(participant)
    return participant


ParticipantDep = Annotated[UUID, Depends(get_participant)]


def _hosting(request: Request) -> list[str]:
    value = request.session.get("hosting")
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def is_host(request: Request, event: Event) -> bool:
    return str(event.id) in _hosting(request)


def remember_host(request: Request, event: Event) -> None:
    hosting = _hosting(request)
    if str(event.id) not in hosting:
        request.session["hosting"] = [*hosting, str(event.id)][-50:]


def require_host(request: Request, event: EventDep) -> Event:
    if not is_host(request, event):
        raise ForbiddenError("Only the host can do that. Open your host link to get the controls.")
    return event


HostEventDep = Annotated[Event, Depends(require_host)]


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"
