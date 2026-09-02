from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.dependencies import (
    CurrentUser,
    ThesisMonitoringServiceDependency,
    ThesisRepositoryDependency,
)
from app.api.schemas import (
    CreateInvestmentThesisRequest,
    CreateThesisConditionRequest,
    ErrorResponse,
    InvestmentThesisResponse,
    RunThesisMonitoringRequest,
    ThesisConditionResponse,
    ThesisMonitoringResponse,
    ThesisStatusHistoryResponse,
    UpdateInvestmentThesisRequest,
    UpdateThesisConditionRequest,
)
from app.database.thesis_repositories import (
    InvalidAggregateError,
    RepositoryConflictError,
    ResourceNotFoundError,
)
from app.domain.metric_calculator import MetricCalculationError
from app.domain.metric_registry import MetricRegistryError
from app.domain.rule_engine import RuleEvaluationError
from app.domain.thesis_models import InvestmentThesis, ThesisCondition, ThesisStatus
from app.services.thesis_monitoring_service import (
    InvalidMonitoringSourceError,
    MonitoringClockError,
    MonitoringDataNotCollectedError,
    MonitoringInsufficientDataError,
    ThesisNotMonitorableError,
)

router = APIRouter(
    prefix="/theses",
    tags=["theses"],
    responses={
        status.HTTP_401_UNAUTHORIZED: { # in OpenAPI doc, this api may return 401 status code with structure matching ErrorResponse
            "model": ErrorResponse,
            "description": "Authentication is required.",
        },
    },
)

@router.post(
    "",
    response_model=InvestmentThesisResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The thesis conflicts with existing data.",
        },
    },
)
async def create_thesis(
    request: CreateInvestmentThesisRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    response: Response,
) -> InvestmentThesisResponse:
    """Create an investment thesis owned by the authenticated user."""

    thesis = InvestmentThesis(
        user_id=current_user.id,
        symbol=request.symbol,
        title=request.title,
        description=request.description,
    )

    try:
        created = await repository.create_thesis(thesis)
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="thesis_conflict",
            message="The investment thesis could not be created.",
        )

    response.headers["Location"] = f"/api/v1/theses/{created.id}"
    return InvestmentThesisResponse.model_validate(created)

@router.get(
    "",
    response_model=list[InvestmentThesisResponse]
)
async def list_theses(
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    symbol:         Annotated[str | None, Query(min_length=1, max_length=15, description="Optional stock-symbol filter")] = None,
    thesis_status:  Annotated[ThesisStatus | None, Query(alias="status", description="Optional status filter")] = None,
    limit:          Annotated[int, Query(ge=1, le=500, description="Maximum number of records to return.")] = 100,
    offset:         Annotated[int, Query(ge=0, description="Number of records to skip.")] = 0,
) -> list[InvestmentThesisResponse]:
    """List investment theses belonging to the authenticated user."""

    theses = await repository.list_theses(
        user_id=current_user.id,
        symbol=symbol,
        status=thesis_status,
        limit=limit,
        offset=offset,
    )

    return [InvestmentThesisResponse.model_validate(thesis) for thesis in theses]

@router.get(
    "/{thesis_id}",
    response_model=InvestmentThesisResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": (
                "The thesis does not exist or is not owned by the user."
            ),
        },
    },
)
async def get_thesis(
    thesis_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> InvestmentThesisResponse:
    """Return one investment thesis owned by the authenticated user."""

    thesis = await repository.get_thesis(
        user_id=current_user.id,
        thesis_id=thesis_id,
    )

    if thesis is None:
        _raise_thesis_not_found()

    return InvestmentThesisResponse.model_validate(thesis)


@router.patch("/{thesis_id}", response_model=InvestmentThesisResponse)
async def update_thesis(
    thesis_id: UUID,
    request: UpdateInvestmentThesisRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> InvestmentThesisResponse:
    """Update thesis content or lifecycle status using optimistic locking."""

    try:
        thesis = await repository.update_thesis(
            user_id=current_user.id,
            thesis_id=thesis_id,
            expected_version=request.expected_version,
            title=request.title,
            description=request.description,
            status=request.status,
            reason=request.reason,
        )
    except ResourceNotFoundError:
        _raise_thesis_not_found()
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="thesis_version_conflict",
            message="The investment thesis has changed; reload and retry.",
        )
    except InvalidAggregateError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="invalid_thesis_transition",
            message="The requested thesis status transition is not allowed.",
        )
    return InvestmentThesisResponse.model_validate(thesis)


@router.post("/{thesis_id}/archive", response_model=InvestmentThesisResponse)
async def archive_thesis(
    thesis_id: UUID,
    request: UpdateInvestmentThesisRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> InvestmentThesisResponse:
    """Archive an owned thesis without deleting audit history."""

    if request.status is not ThesisStatus.ARCHIVED:
        _raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="archive_status_required",
            message="The archive operation requires status archived.",
        )
    return await update_thesis(thesis_id, request, current_user, repository)


@router.get(
    "/{thesis_id}/status-history",
    response_model=list[ThesisStatusHistoryResponse],
)
async def list_thesis_status_history(
    thesis_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> list[ThesisStatusHistoryResponse]:
    """Return lifecycle transitions for one owned thesis."""

    try:
        history = await repository.list_status_history(
            user_id=current_user.id,
            thesis_id=thesis_id,
        )
    except ResourceNotFoundError:
        _raise_thesis_not_found()
    return [ThesisStatusHistoryResponse.model_validate(item) for item in history]


@router.post(
    "/{thesis_id}/conditions",
    response_model=ThesisConditionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": (
                "The thesis does not exist or is not owned by the user."
            ),
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The condition conflicts with existing data.",
        },
    }
)
async def create_condition(
    thesis_id: UUID,
    request: CreateThesisConditionRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    response: Response,
) -> ThesisConditionResponse:
    """Add a deterministic condition to an owned thesis."""

    condition = ThesisCondition(
        thesis_id=thesis_id,
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        kind=request.kind,
        metric=request.metric,
        operator=request.operator,
        threshold=request.threshold,
        consecutive_periods=request.consecutive_periods,
        enabled=request.enabled,
    )

    try:
        created = await repository.create_condition(condition)
    except ResourceNotFoundError:
        _raise_thesis_not_found()
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="condition_conflict",
            message="The thesis condition could not be created.",
        )

    response.headers["Location"] = (
        f"/api/v1/theses/{thesis_id}/conditions/{created.id}"
    )
    return ThesisConditionResponse.model_validate(created)

@router.get(
    "/{thesis_id}/conditions",
    response_model=list[ThesisConditionResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": (
                "The thesis does not exist or is not owned by the user."
            ),
        },
    },
)
async def list_conditions(
    thesis_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
    enabled: Annotated[
        bool | None,
        Query(
            description=(
                "Filter by enabled state. Omit to return all conditions."
            ),
        ),
    ] = None,
) -> list[ThesisConditionResponse]:
    """List deterministic conditions belonging to an owned thesis."""

    try:
        conditions = await repository.list_conditions(
            user_id=current_user.id,
            thesis_id=thesis_id,
            enabled=enabled,
        )
    except ResourceNotFoundError:
        _raise_thesis_not_found()

    return [ThesisConditionResponse.model_validate(condition) for condition in conditions]

@router.get(
    "/{thesis_id}/conditions/{condition_id}",
    response_model=ThesisConditionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": (
                "The condition does not exist or is not owned by the user."
            ),
        },
    },
)
async def get_condition(
    thesis_id: UUID,
    condition_id: UUID,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> ThesisConditionResponse:
    """Return one condition belonging to an owned thesis."""

    condition = await repository.get_condition(
        user_id=current_user.id,
        thesis_id=thesis_id,
        condition_id=condition_id,
    )

    if condition is None:
        _raise_condition_not_found()

    return ThesisConditionResponse.model_validate(condition)


@router.patch(
    "/{thesis_id}/conditions/{condition_id}",
    response_model=ThesisConditionResponse,
)
async def update_condition(
    thesis_id: UUID,
    condition_id: UUID,
    request: UpdateThesisConditionRequest,
    current_user: CurrentUser,
    repository: ThesisRepositoryDependency,
) -> ThesisConditionResponse:
    """Create a new condition version while preserving its stable ID."""

    changes = request.model_dump(exclude={"expected_version"}, exclude_unset=True)
    try:
        condition = await repository.update_condition(
            user_id=current_user.id,
            thesis_id=thesis_id,
            condition_id=condition_id,
            expected_version=request.expected_version,
            changes=changes,
        )
    except ResourceNotFoundError:
        _raise_condition_not_found()
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="condition_version_conflict",
            message="The thesis condition has changed; reload and retry.",
        )
    return ThesisConditionResponse.model_validate(condition)


@router.post(
    "/{thesis_id}/evaluate",
    response_model=ThesisMonitoringResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": (
                "The thesis does not exist or is not owned by the user."
            ),
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": (
                "The thesis cannot currently be evaluated."
            ),
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": ErrorResponse,
            "description": (
                "Persisted observations are insufficient or invalid."
            ),
        },
    },
)
async def evaluate_thesis(
    thesis_id: UUID,
    request: RunThesisMonitoringRequest,
    current_user: CurrentUser,
    service: ThesisMonitoringServiceDependency,
) -> ThesisMonitoringResponse:
    """Run deterministic evaluation for every enabled thesis condition."""

    try:
        result = await service.evaluate_thesis(
            user_id=current_user.id,
            thesis_id=thesis_id,
            source=request.source.value,
            adjustment=request.adjustment,
        )
    except ResourceNotFoundError:
        _raise_thesis_not_found()
    except ThesisNotMonitorableError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="thesis_not_monitorable",
            message=(
                "The investment thesis is not in a monitorable state."
            ),
        )
    except MonitoringDataNotCollectedError:
        _raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="data_not_collected",
            message="No market data has been collected for this request.",
        )
    except (MonitoringInsufficientDataError, MetricCalculationError):
        _raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="insufficient_data",
            message="The collected data is insufficient for this calculation.",
        )
    except MetricRegistryError:
        _raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="unsupported_metric",
            message="The requested metric is not supported.",
        )
    except RuleEvaluationError:
        _raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="rule_evaluation_failed",
            message="The configured rule could not be evaluated.",
        )
    except InvalidMonitoringSourceError:
        _raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid_monitoring_source",
            message="The selected market-data source is invalid.",
        )
    except RepositoryConflictError:
        _raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="monitoring_conflict",
            message=(
                "The monitoring result conflicts with existing data."
            ),
        )
    except MonitoringClockError:
        _raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="monitoring_configuration_error",
            message=(
                "The monitoring service is temporarily unavailable."
            ),
        )

    return ThesisMonitoringResponse.model_validate(result)


def _raise_thesis_not_found() -> NoReturn:
    _raise_api_error(
        status_code=status.HTTP_404_NOT_FOUND,
        code="thesis_not_found",
        message="The investment thesis was not found.",
    )


def _raise_condition_not_found() -> NoReturn:
    _raise_api_error(
        status_code=status.HTTP_404_NOT_FOUND,
        code="condition_not_found",
        message="The thesis condition was not found.",
    )


def _raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> NoReturn:
    """Raise a stable API error without exposing internal exceptions."""

    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    ) from None