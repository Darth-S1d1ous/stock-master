"""HTTP surface for the condition-authoring agent.

The orchestrator, tools, and LLM client stay behind this router.
Clients never supply user_id, thesis symbol, or LLM credentials.
"""

from collections.abc import Awaitable
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.agents.llm import (
    AgentLlmError,
    AgentLlmRequestError,
    AgentLlmResponseError,
)
from app.agents.orchestrator import AgentTurnResult
from app.api.dependencies import (
    AgentRepositoryDependency,
    ConditionAuthorOrchestratorDependency,
    CurrentUser,
    ThesisRepositoryDependency,
)
from app.api.schemas import (
    AgentChatRequest,
    AgentMessageResponse,
    AgentSessionResponse,
    AgentTurnResponse,
    ErrorResponse,
)
from app.database.thesis_repositories import (
    InvalidAggregateError,
    RepositoryConflictError,
    ResourceNotFoundError,
)
from app.domain.agent_models import AgentSession

router = APIRouter(
    tags=["agents"],
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Authentication is required.",
        },
    },
)


@router.post(
    "/theses/{thesis_id}/agent/sessions",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "The thesis does not exist or is not owned by the user.",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "An open agent session already exists for this thesis.",
        },
    },
)
async def create_agent_session(
    thesis_id: UUID,
    current_user: CurrentUser,
    theses: ThesisRepositoryDependency,
    agents: AgentRepositoryDependency,
    response: Response,
) -> AgentSessionResponse:
    """Open a condition-authoring session for an owned thesis.

    At most one open session is allowed per thesis. The symbol is copied
    from the thesis; clients cannot supply ownership fields.
    """

    try:
        thesis = await theses.require_thesis(current_user.id, thesis_id)
    except ResourceNotFoundError:
        _raise_thesis_not_found()

    try:
        created = await agents.create_session(
            AgentSession(
                user_id=current_user.id,
                thesis_id=thesis.id,
                symbol=thesis.symbol,
            )
        )
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="agent_session_conflict",
            message="An open agent session already exists for this thesis.",
        )

    response.headers["Location"] = f"/api/v1/agent/sessions/{created.id}"
    return AgentSessionResponse.model_validate(created)


@router.get(
    "/theses/{thesis_id}/agent/sessions/open",
    response_model=AgentSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": (
                "The thesis or an open agent session was not found."
            ),
        },
    },
)
async def get_open_agent_session(
    thesis_id: UUID,
    current_user: CurrentUser,
    theses: ThesisRepositoryDependency,
    agents: AgentRepositoryDependency,
) -> AgentSessionResponse:
    """Return the open session for an owned thesis, if one exists."""

    try:
        await theses.require_thesis(current_user.id, thesis_id)
    except ResourceNotFoundError:
        _raise_thesis_not_found()

    session = await agents.get_open_session(current_user.id, thesis_id)
    if session is None:
        _raise_session_not_found()
    return AgentSessionResponse.model_validate(session)


@router.get(
    "/agent/sessions/{session_id}/messages",
    response_model=list[AgentMessageResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "The agent session does not exist or is not owned.",
        },
    },
)
async def list_agent_messages(
    session_id: UUID,
    current_user: CurrentUser,
    agents: AgentRepositoryDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AgentMessageResponse]:
    """List append-only messages for an owned agent session."""

    try:
        messages = await agents.list_messages(
            user_id=current_user.id,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )
    except ResourceNotFoundError:
        _raise_session_not_found()
    return [AgentMessageResponse.model_validate(message) for message in messages]


@router.post(
    "/agent/sessions/{session_id}/generate",
    response_model=AgentTurnResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "The agent session does not exist or is not owned.",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The session is closed.",
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ErrorResponse,
            "description": "The language-model provider failed.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "The language-model client is not configured.",
        },
    },
)
async def generate_agent_conditions(
    session_id: UUID,
    current_user: CurrentUser,
    orchestrator: ConditionAuthorOrchestratorDependency,
) -> AgentTurnResponse:
    """Run the built-in generate prompt through the tool loop."""

    return await _run_agent_turn(
        orchestrator.generate(
            user_id=current_user.id,
            session_id=session_id,
        )
    )


@router.post(
    "/agent/sessions/{session_id}/chat",
    response_model=AgentTurnResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "The agent session does not exist or is not owned.",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The session is closed.",
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ErrorResponse,
            "description": "The language-model provider failed.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "The language-model client is not configured.",
        },
    },
)
async def chat_with_agent(
    session_id: UUID,
    request: AgentChatRequest,
    current_user: CurrentUser,
    orchestrator: ConditionAuthorOrchestratorDependency,
) -> AgentTurnResponse:
    """Send one user message through the condition-authoring tool loop."""

    return await _run_agent_turn(
        orchestrator.chat(
            user_id=current_user.id,
            session_id=session_id,
            user_text=request.message,
        )
    )


@router.post(
    "/agent/sessions/{session_id}/close",
    response_model=AgentSessionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "The agent session does not exist or is not owned.",
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The session could not be closed.",
        },
    },
)
async def close_agent_session(
    session_id: UUID,
    current_user: CurrentUser,
    agents: AgentRepositoryDependency,
) -> AgentSessionResponse:
    """Close an owned session. Already-closed sessions are returned as-is."""

    try:
        closed = await agents.close_session(
            user_id=current_user.id,
            session_id=session_id,
        )
    except ResourceNotFoundError:
        _raise_session_not_found()
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="agent_session_conflict",
            message="The agent session could not be closed.",
        )
    return AgentSessionResponse.model_validate(closed)

# ------------------ helper functions ------------------

async def _run_agent_turn(turn: Awaitable[AgentTurnResult]) -> AgentTurnResponse:
    try:
        result = await turn
    except ResourceNotFoundError:
        _raise_session_not_found()
    except InvalidAggregateError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="agent_session_closed",
            message="The agent session is closed.",
        )
    except AgentLlmRequestError:
        _raise_api_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="agent_llm_unreachable",
            message="The language-model provider could not be reached.",
        )
    except AgentLlmResponseError:
        _raise_api_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="agent_llm_invalid_response",
            message="The language-model provider returned an unusable response.",
        )
    except AgentLlmError:
        _raise_api_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_llm_unavailable",
            message="The condition-authoring agent is temporarily unavailable.",
        )
    return AgentTurnResponse.model_validate(result)


def _raise_thesis_not_found() -> NoReturn:
    _raise_api_error(
        status_code=status.HTTP_404_NOT_FOUND,
        code="thesis_not_found",
        message="The investment thesis was not found.",
    )


def _raise_session_not_found() -> NoReturn:
    _raise_api_error(
        status_code=status.HTTP_404_NOT_FOUND,
        code="agent_session_not_found",
        message="The agent session was not found.",
    )


def _raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    ) from None
