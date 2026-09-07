"""Condition-authoring tools. LLM output is untrusted; domain writes are not."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.agents.context import build_metric_catalog
from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import (
    InvalidAggregateError,
    RepositoryConflictError,
    ResourceNotFoundError,
    ThesisRepository,
)
from app.domain.agent_models import (
    AgentConditionWrite,
    AgentConditionWriteAction,
    AgentSession,
)
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    MetricCode,
    ThesisCondition,
)


class ToolErrorCode:
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"

class ToolResult(BaseModel):
    """JSON-serializable result fed back to the model as a tool message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    tool_name: str
    error_code: str | None = None
    error_message: str | None = None
    data: dict[str, Any] | None = None

# Restriction 2: Argument validation is done by pydantic. LLM cannot invent arguments
class CreateConditionToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    kind: ConditionKind
    metric: MetricCode
    operator: ComparisonOperator
    threshold: Decimal
    consecutive_periods: int = Field(default=1, ge=1, le=12)
    enabled: bool = True

    @field_validator("threshold")
    @classmethod
    def require_finite_threshold(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Threshold must be a finite number")
        return value

class UpdateConditionToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    condition_id: UUID
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    kind: ConditionKind | None = None
    metric: MetricCode | None = None
    operator: ComparisonOperator | None = None
    threshold: Decimal | None = None
    consecutive_periods: int | None = Field(default=None, ge=1, le=12)
    enabled: bool | None = None
    @field_validator("threshold")
    @classmethod
    def require_finite_threshold(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("threshold must be finite")
        return value

def _condition_data(condition: ThesisCondition) -> dict[str, Any]:
    return condition.model_dump(mode="json")

def _error(tool_name: str, error_code: ToolErrorCode, error_message: str) -> ToolResult:
    return ToolResult(
        ok=False,
        tool_name=tool_name,
        error_code=error_code,
        error_message=error_message,
    )

def _ok(tool_name: str, data: dict[str, Any]) -> ToolResult:
    return ToolResult(
        ok=True,
        tool_name=tool_name,
        data=data,
    )

# restriction 1: OpenAI - style tool schema for LLM
# { "type": "function", "function": { name, description, parameters } }
TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "list_metric_catalog",
            "description": (
                "List metrics that may appear in a monitoring condition. "
                "Do not invent metric names."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_thesis_conditions",
            "description": (
                "List current monitoring conditions on the thesis bound to "
                "this session."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_condition",
            "description": (
                "Create a deterministic monitoring condition on the current "
                "thesis. thesis_id is assigned by the system."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [kind.value for kind in ConditionKind],
                    },
                    "metric": {
                        "type": "string",
                        "enum": [metric.value for metric in MetricCode],
                    },
                    "operator": {
                        "type": "string",
                        "enum": [
                            operator.value for operator in ComparisonOperator
                        ],
                    },
                    "threshold": {"type": "number"},
                    "consecutive_periods": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                    },
                    "enabled": {"type": "boolean"},
                },
                "required": ["name", "kind", "metric", "operator", "threshold"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_condition",
            "description": (
                "Update an existing condition on the current thesis. "
                "expected_version is required."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "condition_id": {"type": "string", "format": "uuid"},
                    "expected_version": {"type": "integer", "minimum": 1},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [kind.value for kind in ConditionKind],
                    },
                    "metric": {
                        "type": "string",
                        "enum": [metric.value for metric in MetricCode],
                    },
                    "operator": {
                        "type": "string",
                        "enum": [
                            operator.value for operator in ComparisonOperator
                        ],
                    },
                    "threshold": {"type": "number"},
                    "consecutive_periods": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                    },
                    "enabled": {"type": "boolean"},
                },
                "required": ["condition_id", "expected_version"],
                "additionalProperties": False,
            },
        },
    },
)

class ConditionAuthorTools:
    """Dispatch named tools against owned thesis and agent repositories."""

    def __init__(
        self,
        *,
        theses: ThesisRepository,
        agents: AgentRepository,
    ) -> None:
        self._theses = theses
        self._agents = agents
    
    async def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: UUID,
        session: AgentSession,
        message_id: UUID | None = None,
    ) -> ToolResult:
        if session.user_id != user_id:
            return _error(
                tool_name,
                ToolErrorCode.FORBIDDEN,
                "Session is not owned by the current user.",
            )
        
        if tool_name == "list_metric_catalog":
            return self._list_metric_catalog()
        if tool_name == "list_thesis_conditions":
            return await self._list_thesis_conditions(
                user_id=user_id,
                session=session,
            )
        if tool_name == "create_condition":
            return await self._create_condition(
                arguments=arguments,
                user_id=user_id,
                session=session,
                message_id=message_id,
            )
        if tool_name == "update_condition":
            return await self._update_condition(
                arguments=arguments,
                user_id=user_id,
                session=session,
                message_id=message_id,
            )
        return _error(
            tool_name,
            ToolErrorCode.UNKNOWN_TOOL,
            f"Unknown tool: {tool_name}",
        )
    def _list_metric_catalog(self) -> ToolResult:
        catalog = [entry.model_dump(mode="json") for entry in build_metric_catalog()]
        return _ok("list_metric_catalog", {"metrics": catalog})
    async def _list_thesis_conditions(
        self,
        *,
        user_id: UUID,
        session: AgentSession,
    ) -> ToolResult:
        try:
            conditions = await self._theses.list_conditions(
                user_id,
                session.thesis_id,
            )
        except ResourceNotFoundError:
            return _error(
                "list_thesis_conditions",
                ToolErrorCode.NOT_FOUND,
                "Thesis not found or inaccessible.",
            )
        return _ok(
            "list_thesis_conditions",
            {"conditions": [_condition_data(item) for item in conditions]},
        )
    async def _create_condition(
        self,
        *,
        arguments: dict[str, Any],
        user_id: UUID,
        session: AgentSession,
        message_id: UUID | None,
    ) -> ToolResult:
        if message_id is None:
            return _error(
                "create_condition",
                ToolErrorCode.INVALID_ARGUMENTS,
                "message_id is required before creating a condition.",
            )
        try:
            args = CreateConditionToolArgs.model_validate(arguments)
        except ValidationError as error:
            return _error(
                "create_condition",
                ToolErrorCode.INVALID_ARGUMENTS,
                error.errors()[0]["msg"],
            )
        condition = ThesisCondition(
            thesis_id=session.thesis_id,
            user_id=user_id,
            name=args.name,
            description=args.description,
            kind=args.kind,
            metric=args.metric,
            operator=args.operator,
            threshold=args.threshold,
            consecutive_periods=args.consecutive_periods,
            enabled=args.enabled,
        )
        try:
            created = await self._theses.create_condition(condition)
            await self._agents.record_condition_write(
                AgentConditionWrite(
                    session_id=session.id,
                    message_id=message_id,
                    user_id=user_id,
                    thesis_id=session.thesis_id,
                    condition_id=created.id,
                    action=AgentConditionWriteAction.CREATE,
                )
            )
        except ResourceNotFoundError:
            return _error(
                "create_condition",
                ToolErrorCode.NOT_FOUND,
                "Thesis or tool message not found or inaccessible.",
            )
        except RepositoryConflictError:
            return _error(
                "create_condition",
                ToolErrorCode.CONFLICT,
                "The condition could not be created.",
            )
        except InvalidAggregateError:
            return _error(
                "create_condition",
                ToolErrorCode.FORBIDDEN,
                "The condition write does not match this session.",
            )
        return _ok("create_condition", {"condition": _condition_data(created)})
    async def _update_condition(
        self,
        *,
        arguments: dict[str, Any],
        user_id: UUID,
        session: AgentSession,
        message_id: UUID | None,
    ) -> ToolResult:
        if message_id is None:
            return _error(
                "update_condition",
                ToolErrorCode.INVALID_ARGUMENTS,
                "message_id is required before updating a condition.",
            )
        try:
            args = UpdateConditionToolArgs.model_validate(arguments)
        except ValidationError as error:
            return _error(
                "update_condition",
                ToolErrorCode.INVALID_ARGUMENTS,
                error.errors()[0]["msg"],
            )
        changes = args.model_dump(
            exclude={"condition_id", "expected_version"},
            exclude_unset=True,
        )
        if not changes:
            return _error(
                "update_condition",
                ToolErrorCode.INVALID_ARGUMENTS,
                "at least one condition field must be changed",
            )
        try:
            updated = await self._theses.update_condition(
                user_id=user_id,
                thesis_id=session.thesis_id,
                condition_id=args.condition_id,
                expected_version=args.expected_version,
                changes=changes,
            )
            await self._agents.record_condition_write(
                AgentConditionWrite(
                    session_id=session.id,
                    message_id=message_id,
                    user_id=user_id,
                    thesis_id=session.thesis_id,
                    condition_id=updated.id,
                    action=AgentConditionWriteAction.UPDATE,
                )
            )
        except ResourceNotFoundError:
            return _error(
                "update_condition",
                ToolErrorCode.NOT_FOUND,
                "Condition or tool message not found or inaccessible.",
            )
        except RepositoryConflictError:
            return _error(
                "update_condition",
                ToolErrorCode.CONFLICT,
                "The thesis condition has changed; reload and retry.",
            )
        except InvalidAggregateError:
            return _error(
                "update_condition",
                ToolErrorCode.FORBIDDEN,
                "The condition write does not match this session.",
            )
        return _ok("update_condition", {"condition": _condition_data(updated)})