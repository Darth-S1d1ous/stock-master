"""Persistence for condition-authoring agent sessions.

Transactions are owned by the application layer. Every owned read filters by
``user_id``. Messages and condition-write records are append-only.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.agent_tables import (
    AgentConditionWriteTable,
    AgentMemoryTable,
    AgentMessageTable,
    AgentSessionTable,
)
from app.database.thesis_repositories import (
    InvalidAggregateError,
    RepositoryConflictError,
    ResourceNotFoundError,
    ThesisRepository,
)
from app.domain.agent_models import (
    AgentConditionWrite,
    AgentConditionWriteAction,
    AgentMemory,
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentSessionStatus,
)


class AgentRepository:
    """Persistence operations for agent conversation aggregates.
    The repository never commits or rolls back the session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session: AsyncSession = session
        self._theses = ThesisRepository(session)

    async def create_session(self, session: AgentSession) -> AgentSession:
        thesis = await self._theses.require_thesis(session.user_id, session.thesis_id)
        if session.symbol != thesis.symbol:
            raise InvalidAggregateError("Session symbol does not match thesis symbol")

        existing = await self.get_open_session(session.user_id, session.thesis_id)
        if existing is not None:
            raise RepositoryConflictError("An open session already exists for this thesis")
        
        statement = (
            insert(AgentSessionTable)
            .values(
                id=session.id,
                user_id=session.user_id,
                thesis_id=session.thesis_id,
                symbol=session.symbol,
                status=session.status.value,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            .on_conflict_do_nothing(index_elements=[AgentSessionTable.id])
            .returning(AgentSessionTable.id)
        )

        try:
            result = await self._session.execute(statement)
            inserted_id = result.scalar_one_or_none()
            if inserted_id is None:
                raise RepositoryConflictError("Agent session already exists or is inaccessible")
            await self._session.flush()
        except IntegrityError as error:
            raise RepositoryConflictError("An open agent session already exists for this thesis") from error
        
        return session

    async def get_session(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> AgentSession | None:
        statement: Select[tuple[AgentSessionTable]] = select(
            AgentSessionTable
        ).where(
            AgentSessionTable.id == session_id,
            AgentSessionTable.user_id == user_id,
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._session_from_row(row) if row is not None else None
        
    async def require_session(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> AgentSession:
        session = await self.get_session(user_id=user_id, session_id=session_id)
        if session is None:
            raise ResourceNotFoundError("Agent session not found or inaccessible")
        return session

    async def get_open_session(
        self,
        user_id: UUID,
        thesis_id: UUID,
    ) -> AgentSession | None:
        statement: Select[tuple[AgentSessionTable]] = (
            select(AgentSessionTable)
            .where(
                AgentSessionTable.user_id == user_id,
                AgentSessionTable.thesis_id == thesis_id,
                AgentSessionTable.status == AgentSessionStatus.OPEN.value,
            )
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()

        return self._session_from_row(row) if row is not None else None

    async def close_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> AgentSession:
        current = await self.require_session(user_id=user_id, session_id=session_id)
        if current.status is AgentSessionStatus.CLOSED:
            return current
        statement = (
            update(AgentSessionTable)
            .where(
                AgentSessionTable.id == session_id,
                AgentSessionTable.user_id == user_id,
                AgentSessionTable.status == AgentSessionStatus.OPEN.value,
            )
            .values(
                status=AgentSessionStatus.CLOSED.value,
                updated_at=datetime.now(UTC),
            )
            .returning(AgentSessionTable)
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            raise RepositoryConflictError("Agent session could not be closed")
        await self._session.flush()

        return self._session_from_row(row)
    
    async def append_message(self, message: AgentMessage) -> AgentMessage:
        session = await self.require_session(
            user_id=message.user_id,
            session_id=message.session_id,
        )
        if session.status is AgentSessionStatus.CLOSED:
            raise InvalidAggregateError("Cannot append messages to a closed session")
        statement = (
            insert(AgentMessageTable)
            .values(
                id=message.id,
                session_id=message.session_id,
                user_id=message.user_id,
                role=message.role.value,
                content=message.content,
                tool_name=message.tool_name,
                tool_call_id=message.tool_call_id,
                model=message.model,
                prompt_version=message.prompt_version,
                created_at=message.created_at,
            )
            .on_conflict_do_nothing(index_elements=[AgentMessageTable.id])
            .returning(AgentMessageTable.id)
        )
        result = await self._session.execute(statement)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            raise RepositoryConflictError("Agent message already exists or is inaccessible")
        await self._touch_session(session_id=session.id, user_id=session.user_id)
        await self._session.flush()

        return message
    
    async def list_messages(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentMessage]:
        self._validate_pagination(limit=limit, offset=offset)
        await self.require_session(user_id=user_id, session_id=session_id)
        statement: Select[tuple[AgentMessageTable]] = (
            select(AgentMessageTable)
            .where(
                AgentMessageTable.session_id == session_id,
                AgentMessageTable.user_id == user_id,
            )
            .order_by(AgentMessageTable.created_at, AgentMessageTable.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)

        return [self._message_from_row(row) for row in result.scalars()]

    async def upsert_memory(self, memory: AgentMemory) -> AgentMemory:
        await self.require_session(user_id=memory.user_id, session_id=memory.session_id)
        statement = (
            insert(AgentMemoryTable)
            .values(
                id=memory.id,
                session_id=memory.session_id,
                user_id=memory.user_id,
                summary=memory.summary,
                message_count_at_summary=memory.message_count_at_summary,
                updated_at=memory.updated_at,
            )
            .on_conflict_do_update(
                constraint="agent_memory_session_identity",
                set_={
                    "summary": memory.summary,
                    "message_count_at_summary": memory.message_count_at_summary,
                    "updated_at": memory.updated_at,
                },
            )
            .returning(AgentMemoryTable)
        )
        result = await self._session.execute(statement)
        row = result.scalar_one()
        await self._session.flush()
        return self._memory_from_row(row)
    async def get_memory(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> AgentMemory | None:
        await self.require_session(user_id=user_id, session_id=session_id)
        statement: Select[tuple[AgentMemoryTable]] = select(AgentMemoryTable).where(
            AgentMemoryTable.session_id == session_id,
            AgentMemoryTable.user_id == user_id,
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        return self._memory_from_row(row) if row is not None else None
    async def record_condition_write(
        self,
        write: AgentConditionWrite,
    ) -> AgentConditionWrite:
        session = await self.require_session(
            user_id=write.user_id,
            session_id=write.session_id,
        )
        if write.thesis_id != session.thesis_id:
            raise InvalidAggregateError(
                "Condition write thesis must match the agent session thesis"
            )
        messages = await self.list_messages(
            user_id=write.user_id,
            session_id=write.session_id,
            limit=500,
        )
        if write.message_id not in {item.id for item in messages}:
            raise ResourceNotFoundError("Agent message not found or inaccessible")
        await self._theses.require_condition(
            user_id=write.user_id,
            thesis_id=write.thesis_id,
            condition_id=write.condition_id,
        )
        statement = (
            insert(AgentConditionWriteTable)
            .values(
                id=write.id,
                session_id=write.session_id,
                message_id=write.message_id,
                user_id=write.user_id,
                thesis_id=write.thesis_id,
                condition_id=write.condition_id,
                action=write.action.value,
                created_at=write.created_at,
            )
            .on_conflict_do_nothing(index_elements=[AgentConditionWriteTable.id])
            .returning(AgentConditionWriteTable.id)
        )
        result = await self._session.execute(statement)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            raise RepositoryConflictError(
                "Agent condition write already exists or is inaccessible"
            )
        await self._session.flush()

        return write

    async def list_condition_writes(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
    ) -> list[AgentConditionWrite]:
        await self.require_session(user_id=user_id, session_id=session_id)
        statement: Select[tuple[AgentConditionWriteTable]] = (
            select(AgentConditionWriteTable)
            .where(
                AgentConditionWriteTable.session_id == session_id,
                AgentConditionWriteTable.user_id == user_id,
            )
            .order_by(
                AgentConditionWriteTable.created_at,
                AgentConditionWriteTable.id,
            )
        )
        result = await self._session.execute(statement)

        return [self._write_from_row(row) for row in result.scalars()]
    
    async def _touch_session(self, *, session_id: UUID, user_id: UUID) -> None:
        await self._session.execute(
            update(AgentSessionTable)
            .where(
                AgentSessionTable.id == session_id,
                AgentSessionTable.user_id == user_id,
            )
            .values(updated_at=datetime.now(UTC))
        )

    @staticmethod
    def _validate_pagination(*, limit: int, offset: int) -> None:
        if not 1 <= limit <= 500:
            raise ValueError("Limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("Offset cannot be negative")

    @staticmethod
    def _session_from_row(row: AgentSessionTable) -> AgentSession:
        return AgentSession(
            id=row.id,
            user_id=row.user_id,
            thesis_id=row.thesis_id,
            symbol=row.symbol,
            status=AgentSessionStatus(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _message_from_row(row: AgentMessageTable) -> AgentMessage:
        return AgentMessage(
            id=row.id,
            session_id=row.session_id,
            user_id=row.user_id,
            role=AgentMessageRole(row.role),
            content=row.content,
            tool_name=row.tool_name,
            tool_call_id=row.tool_call_id,
            model=row.model,
            prompt_version=row.prompt_version,
            created_at=row.created_at,
        )
    @staticmethod
    def _memory_from_row(row: AgentMemoryTable) -> AgentMemory:
        return AgentMemory(
            id=row.id,
            session_id=row.session_id,
            user_id=row.user_id,
            summary=row.summary,
            message_count_at_summary=row.message_count_at_summary,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _write_from_row(row: AgentConditionWriteTable) -> AgentConditionWrite:
        return AgentConditionWrite(
            id=row.id,
            session_id=row.session_id,
            message_id=row.message_id,
            user_id=row.user_id,
            thesis_id=row.thesis_id,
            condition_id=row.condition_id,
            action=AgentConditionWriteAction(row.action),
            created_at=row.created_at,
        )