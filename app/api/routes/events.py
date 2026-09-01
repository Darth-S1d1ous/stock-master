from datetime import date
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.dependencies import CurrentUser, ThesisRepositoryDependency
from app.api.schemas import (
    CreateEventFeedbackRequest,
    DomainEventResponse,
    ErrorResponse,
    EventEvidenceResponse,
    EventFeedbackResponse,
    UpdateEventStatusRequest,
)
from app.database.thesis_repositories import ResourceNotFoundError
from app.domain.event_models import EventFeedback, EventSeverity, EventStatus

router = APIRouter(
    prefix="/events",
    tags=["events"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Authentication is required.",
        }
    },
)


@router.get("", response_model=list[DomainEventResponse])
async def list_events(
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    symbol: Annotated[str | None, Query(min_length=1, max_length=15)] = None,
    thesis_id: UUID | None = None,
    severity: EventSeverity | None = None,
    event_status: Annotated[EventStatus | None, Query(alias="status")] = None,
    occurred_from: date | None = None,
    occurred_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DomainEventResponse]:
    """List only events owned by the authenticated user."""

    if occurred_from is not None and occurred_to is not None and occurred_from > occurred_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "invalid_date_range",
                "message": "occurred_from cannot be later than occurred_to.",
            },
        )
    events = await repository.list_events(
        user_id=current_user.id,
        thesis_id=thesis_id,
        symbol=symbol,
        severity=severity,
        status=event_status,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    return [DomainEventResponse.model_validate(event) for event in events]


@router.get("/{event_id}", response_model=DomainEventResponse)
async def get_event(
    event_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> DomainEventResponse:
    """Return one event after ownership filtering."""

    event = await repository.get_event(user_id=current_user.id, event_id=event_id)
    if event is None:
        _raise_event_not_found()
    return DomainEventResponse.model_validate(event)


@router.get("/{event_id}/evidence", response_model=list[EventEvidenceResponse])
async def list_event_evidence(
    event_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> list[EventEvidenceResponse]:
    """Return immutable evidence for one owned event."""

    try:
        evidence = await repository.list_event_evidence(
            user_id=current_user.id,
            event_id=event_id,
        )
    except ResourceNotFoundError:
        _raise_event_not_found()
    return [EventEvidenceResponse.model_validate(item) for item in evidence]


@router.patch("/{event_id}/status", response_model=DomainEventResponse)
async def update_event_status(
    event_id: UUID,
    request: UpdateEventStatusRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> DomainEventResponse:
    """Change the workflow status of one owned event."""

    try:
        event = await repository.update_event_status(
            user_id=current_user.id,
            event_id=event_id,
            event_status=request.status,
        )
    except ResourceNotFoundError:
        _raise_event_not_found()
    return DomainEventResponse.model_validate(event)


@router.post(
    "/{event_id}/feedback",
    response_model=EventFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def append_event_feedback(
    event_id: UUID,
    request: CreateEventFeedbackRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    response: Response,
) -> EventFeedbackResponse:
    """Append feedback without replacing earlier user feedback."""

    try:
        feedback = await repository.save_feedback(
            EventFeedback(
                event_id=event_id,
                user_id=current_user.id,
                feedback_type=request.feedback_type,
                comment=request.comment,
            )
        )
    except ResourceNotFoundError:
        _raise_event_not_found()
    response.headers["Location"] = f"/api/v1/events/{event_id}/feedback/{feedback.id}"
    return EventFeedbackResponse.model_validate(feedback)


@router.get(
    "/{event_id}/feedback",
    response_model=list[EventFeedbackResponse],
)
async def list_event_feedback(
    event_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EventFeedbackResponse]:
    """Return append-only feedback history for one owned event."""

    try:
        feedback = await repository.list_feedback_history(
            user_id=current_user.id,
            event_id=event_id,
            limit=limit,
            offset=offset,
        )
    except ResourceNotFoundError:
        _raise_event_not_found()
    return [EventFeedbackResponse.model_validate(item) for item in feedback]


def _raise_event_not_found() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "event_not_found",
            "message": "The domain event was not found.",
        },
    ) from None
