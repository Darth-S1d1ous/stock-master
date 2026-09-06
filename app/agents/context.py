"""Assemble deterministic context for the condition-authoring agent.

This module never calls a model. It only reads owned thesis data, session
memory, and the metric registry allow-list.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import ThesisRepository
from app.domain.agent_models import (
    AgentConditionWrite,
    AgentMemory,
    AgentMessage,
    AgentSession,
)
from app.domain.metric_registry import METRIC_REGISTRY, MetricInputKind
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
)

_METRIC_DESCRIPTIONS: Mapping[MetricCode, str] = {
    MetricCode.DAILY_PRICE_CHANGE_PERCENT: (
        "Percent change from the previous daily close to the latest close."
    ),
    MetricCode.VOLUME_RATIO_20D: (
        "Latest volume divided by the average volume of the prior 20 sessions."
    ),
    MetricCode.PE_RATIO: "Latest observed price-to-earnings ratio.",
    MetricCode.PE_RATIO_CHANGE_PERCENT: (
        "Percent change between the latest PE and the previous snapshot."
    ),
    MetricCode.PRICE_TO_BOOK_RATIO: "Latest observed price-to-book ratio.",
    MetricCode.PRICE_TO_BOOK_CHANGE_PERCENT: (
        "Percent change between the latest PB and the previous snapshot."
    ),
    MetricCode.EBITDA: "Latest observed EBITDA.",
}

class MetricCatalogEntry(BaseModel):
    """One metric the agent is allowed to use in a condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    metric: MetricCode
    input_kind: MetricInputKind
    required_observations: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=300)

class ThesisSnapshot(BaseModel):
    """One owned thesis and its current conditions for a symbol."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    thesis: InvestmentThesis
    conditions: tuple[ThesisCondition, ...]

class AgentContextPack(BaseModel):
    """Read-only bundle passed to the orchestrator / LLM prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session: AgentSession
    current_thesis: InvestmentThesis
    related_theses: tuple[ThesisSnapshot, ...]
    metric_catalog: tuple[MetricCatalogEntry, ...]
    allowed_kinds: tuple[ConditionKind, ...]
    allowed_operators: tuple[ComparisonOperator, ...]
    messages: tuple[AgentMessage, ...]
    memory: AgentMemory | None
    condition_writes: tuple[AgentConditionWrite, ...]

    @property
    def is_current(self) -> bool:
        return self.session.thesis_id == self.current_thesis.id

def build_metric_catalog() -> tuple[MetricCatalogEntry, ...]:

    entries: list[MetricCatalogEntry] = []
    for metric in MetricCode:
        definition = METRIC_REGISTRY[metric]
        entries.append(
            MetricCatalogEntry(
                metric=metric,
                input_kind=definition.input_kind,
                required_observations=definition.required_observations,
                description=_METRIC_DESCRIPTIONS[metric],
            )
        )
    return tuple(entries)

def render_context_pack(pack: AgentContextPack) -> str:
    """Render a stable, human-readable prompt block."""

    lines: list[str] = [
        f"Symbol: {pack.session.symbol}",
        f"Session: {pack.session.id} ({pack.session.status.value})",
        "",
        "Current thesis:",
        f"- id={pack.current_thesis.id}",
        f"- status={pack.current_thesis.status.value}",
        f"- title={pack.current_thesis.title}",
        f"- description={pack.current_thesis.description}",
        "",
        "Related theses for this user and symbol:",
    ]    

    for snapshot in pack.related_theses:
        marker = "current" if snapshot.thesis.id == pack.current_thesis.id else "related"
        lines.append(
            f"- [{marker}] {snapshot.thesis.id} "
            f"{snapshot.thesis.status.value}: {snapshot.thesis.title}"
        )
        if not snapshot.conditions:
            lines.append("  conditions: none")
            continue
        for condition in snapshot.conditions:
            lines.append(
                "  - "
                f"{condition.name}: {condition.kind.value} "
                f"{condition.metric.value} {condition.operator.value} "
                f"{condition.threshold} "
                f"(enabled={condition.enabled})"
            )
    lines.extend(["", "Allowed metrics:"])
    for entry in pack.metric_catalog:
        lines.append(
            f"- {entry.metric.value} "
            f"({entry.input_kind.value}, n>={entry.required_observations}): "
            f"{entry.description}"
        )
    lines.append("")
    lines.append(
        "Allowed kinds: "
        + ", ".join(kind.value for kind in pack.allowed_kinds)
    )
    lines.append(
        "Allowed operators: "
        + ", ".join(operator.value for operator in pack.allowed_operators)
    )
    if pack.memory is not None:
        lines.extend(
            [
                "",
                "Session memory summary:",
                pack.memory.summary,
                f"(covers {pack.memory.message_count_at_summary} messages)",
            ]
        )
    lines.extend(["", "Session messages:"])
    if not pack.messages:
        lines.append("- none")
    else:
        for message in pack.messages:
            tool = ""
            if message.tool_name is not None:
                tool = f" tool={message.tool_name}"
            lines.append(f"- {message.role.value}{tool}: {message.content}")
    if pack.condition_writes:
        lines.extend(["", "Conditions already written in this session:"])
        for write in pack.condition_writes:
            lines.append(
                f"- {write.action.value} condition={write.condition_id} "
                f"from message={write.message_id}"
            )
    return "\n".join(lines)

@dataclass(frozen=True, slots=True)
class AgentContextAssembler:
    """Load owned research state into an AgentContextPack."""

    theses: ThesisRepository
    agents: AgentRepository

    async def assemble(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> AgentContextPack:
        session = await self.agents.require_session(
            user_id=user_id,
            session_id=session_id,
        )
        current_thesis = await self.theses.require_thesis(
            user_id=user_id,
            thesis_id=session.thesis_id,
        )
        related_theses = await self._load_related_theses(
            user_id=user_id,
            symbol=session.symbol,
        )
        messages = await self.agents.list_messages(
            user_id=user_id,
            session_id=session_id,
        )
        memory = await self.agents.get_memory(
            user_id=user_id,
            session_id=session_id,
        )
        condition_writes = await self.agents.list_condition_writes(
            user_id=user_id,
            session_id=session_id,
        )
        return AgentContextPack(
            session=session,
            current_thesis=current_thesis,
            related_theses=related_theses,
            metric_catalog=build_metric_catalog(),
            allowed_kinds=tuple(ConditionKind),
            allowed_operators=tuple(ComparisonOperator),
            messages=tuple(messages),
            memory=memory,
            condition_writes=tuple(condition_writes),
        )

    # define theses with the same SYMBOL as "related"
    async def _load_related_theses(
        self,
        *,
        user_id: UUID,
        symbol: str,
    ) -> tuple[ThesisSnapshot, ...]:
        theses = await self.theses.list_theses(user_id, symbol=symbol)
        snapshots: list[ThesisSnapshot] = []
        for thesis in theses:
            conditions = await self.theses.list_conditions(
                user_id,
                thesis.id,
            )

            snapshots.append(
                ThesisSnapshot(thesis=thesis, conditions=tuple(conditions))
            )
        return tuple(snapshots)