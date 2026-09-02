"""Orchestrate reliable and auditable stock-data ingestion runs.

This module coordinates single-symbol and active-thesis batch refreshes. It
normalizes and deduplicates symbols, prevents concurrent runs for the same
provider with a PostgreSQL advisory lock, and processes symbols sequentially
while enforcing request intervals, timeouts, retries, and circuit breaking.

The runner delegates provider access and atomic market-data persistence to
``StockIngestionService``. It records both run-level summaries and per-symbol
outcomes so non-interactive callers can inspect successes, partial failures,
and sanitized provider errors without exposing sensitive implementation details.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_sources.base import OutputSize, StockDataSource
from app.data_sources.provider_factory import create_data_source
from app.database.domain_tables import (
    IngestionRunItemTable,
    IngestionRunTable,
    InvestmentThesisTable,
)
from app.database.session import AsyncSessionFactory
from app.services.stock_ingestion_service import IngestionResult, StockIngestionService

_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")


@dataclass(frozen=True, slots=True)
class SymbolIngestionOutcome:
    """Sanitized result for one symbol in a batch."""

    symbol: str
    succeeded: bool
    daily_bars_processed: int = 0
    fundamental_snapshot_date: date | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionRunOutcome:
    """Summary returned to a non-interactive caller."""

    run_id: UUID
    source: str
    status: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    items: tuple[SymbolIngestionOutcome, ...]


class ProviderCircuitOpenError(RuntimeError):
    """Raised after repeated provider failures open the local circuit."""


class IngestionRunConflictError(RuntimeError):
    """Raised when another process holds the provider ingestion lock."""


class IngestionRunner:
    """Run sequential, auditable ingestion jobs without a task broker."""

    def __init__(
        self,
        *,
        provider: str,
        output_size: OutputSize = "compact",
        timeout_seconds: float = 45.0,
        minimum_interval_seconds: float = 1.0,
        failure_threshold: int = 3,
        max_attempts: int = 2,
    ) -> None:
        self._provider = provider.strip().lower()
        self._output_size = output_size
        self._timeout_seconds = timeout_seconds
        self._minimum_interval_seconds = minimum_interval_seconds
        self._failure_threshold = failure_threshold
        self._max_attempts = max_attempts
        self._consecutive_failures = 0
        self._last_request_at: float | None = None

    async def run_symbol(self, symbol: str) -> IngestionRunOutcome:
        """Refresh one validated stock symbol."""

        return await self.run([self._normalize_symbol(symbol)], mode="symbol")

    async def run_active(self) -> IngestionRunOutcome:
        """Refresh unique symbols from active or challenged theses."""

        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(InvestmentThesisTable.symbol)
                .where(InvestmentThesisTable.status.in_(("active", "challenged")))
                .distinct()
                .order_by(InvestmentThesisTable.symbol)
            )
            symbols = list(result.scalars())
        return await self.run(symbols, mode="active")

    async def run(self, symbols: list[str], *, mode: str) -> IngestionRunOutcome:
        """Run a sequential batch and persist the run and item outcomes."""

        normalized_symbols = sorted({self._normalize_symbol(value) for value in symbols})
        run_id = uuid4()
        started_at = datetime.now(UTC)

        # pg_try_advisory_lock
        async with AsyncSessionFactory() as lock_session:
            lock_key = f"stock-master-bot:ingestion:{self._provider}"
            acquired = bool(
                await lock_session.scalar(
                    text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
                    {"lock_key": lock_key},
                )
            )
            if not acquired:
                raise IngestionRunConflictError(
                    "An ingestion run for this provider is already active."
                )
            try:
                await self._create_run(
                    run_id=run_id,
                    mode=mode,
                    requested_count=len(normalized_symbols),
                    started_at=started_at,
                )
                if not normalized_symbols:
                    return await self._complete_run(run_id, ())
                outcomes = await self._run_symbols(run_id, normalized_symbols)
                return await self._complete_run(run_id, outcomes)
            finally:
                await lock_session.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                    {"lock_key": lock_key},
                )
                await lock_session.commit()

    async def _run_symbols(
        self,
        run_id: UUID,
        symbols: list[str],
    ) -> tuple[SymbolIngestionOutcome, ...]:
        outcomes: list[SymbolIngestionOutcome] = []
        async with create_data_source(self._provider) as data_source:
            for symbol in symbols:
                if self._consecutive_failures >= self._failure_threshold:
                    outcome = SymbolIngestionOutcome(
                        symbol=symbol,
                        succeeded=False,
                        error_code="provider_circuit_open",
                        error_message="Provider circuit opened after repeated failures.",
                    )
                    await self._save_failed_item(run_id, outcome)
                    outcomes.append(outcome)
                    continue
                await self._respect_rate_limit()
                outcome = await self._refresh_with_retry(run_id, symbol, data_source)
                outcomes.append(outcome)
        return tuple(outcomes)

    async def _refresh_with_retry(
        self,
        run_id: UUID,
        symbol: str,
        data_source: StockDataSource,
    ) -> SymbolIngestionOutcome:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with AsyncSessionFactory() as session, session.begin():
                        service = StockIngestionService(session, data_source)
                        result = await asyncio.wait_for(
                            service.refresh_symbol(symbol, self._output_size),
                            timeout=self._timeout_seconds,
                        )
                        await self._save_success_item(session, run_id, result)
                self._consecutive_failures = 0
                return SymbolIngestionOutcome(
                    symbol=symbol,
                    succeeded=True,
                    daily_bars_processed=result.daily_bars_processed,
                    fundamental_snapshot_date=result.fundamental_snapshot_date,
                )
            except Exception as exc:  # noqa: BLE001  # retry loop must capture any failure to retry and report
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))

        self._consecutive_failures += 1
        outcome = SymbolIngestionOutcome(
            symbol=symbol,
            succeeded=False,
            error_code=self._error_code(last_error),
            error_message=self._safe_error_message(last_error),
        )
        await self._save_failed_item(run_id, outcome)
        return outcome

    async def _respect_rate_limit(self) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._last_request_at is not None:
            remaining = self._minimum_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_request_at = loop.time()

    async def _create_run(
        self,
        *,
        run_id: UUID,
        mode: str,
        requested_count: int,
        started_at: datetime,
    ) -> None:
        async with AsyncSessionFactory() as session, session.begin():
            session.add(
                IngestionRunTable(
                    id=run_id,
                    source=self._provider,
                    mode=mode,
                    status="running",
                    requested_count=requested_count,
                    succeeded_count=0,
                    failed_count=0,
                    started_at=started_at,
                )
            )

    @staticmethod
    async def _save_success_item(
        session: AsyncSession,
        run_id: UUID,
        result: IngestionResult,
    ) -> None:
        session.add(
            IngestionRunItemTable(
                id=uuid4(),
                run_id=run_id,
                symbol=result.symbol,
                status="succeeded",
                daily_bars_processed=result.daily_bars_processed,
                fundamental_snapshot_date=result.fundamental_snapshot_date,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )

    async def _save_failed_item(
        self,
        run_id: UUID,
        outcome: SymbolIngestionOutcome,
    ) -> None:
        async with AsyncSessionFactory() as session, session.begin():
            session.add(
                IngestionRunItemTable(
                    id=uuid4(),
                    run_id=run_id,
                    symbol=outcome.symbol,
                    status="failed",
                    daily_bars_processed=0,
                    error_code=outcome.error_code,
                    error_message=outcome.error_message,
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                )
            )

    async def _complete_run(
        self,
        run_id: UUID,
        outcomes: tuple[SymbolIngestionOutcome, ...],
    ) -> IngestionRunOutcome:
        succeeded = sum(item.succeeded for item in outcomes)
        failed = len(outcomes) - succeeded
        status = "succeeded" if failed == 0 else "failed" if succeeded == 0 else "partial"
        async with AsyncSessionFactory() as session, session.begin():
            await session.execute(
                update(IngestionRunTable)
                .where(IngestionRunTable.id == run_id)
                .values(
                    status=status,
                    succeeded_count=succeeded,
                    failed_count=failed,
                    completed_at=datetime.now(UTC),
                )
            )
        return IngestionRunOutcome(
            run_id=run_id,
            source=self._provider,
            status=status,
            requested_count=len(outcomes),
            succeeded_count=succeeded,
            failed_count=failed,
            items=outcomes,
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid stock symbol.")
        return normalized

    @staticmethod
    def _error_code(error: Exception | None) -> str:
        if isinstance(error, TimeoutError):
            return "data_source_timeout"
        if isinstance(error, ValueError):
            return "invalid_provider_data"
        return "data_source_failure"

    @staticmethod
    def _safe_error_message(error: Exception | None) -> str:
        if isinstance(error, TimeoutError):
            return "The provider request exceeded the configured timeout."
        if isinstance(error, ValueError):
            return "The provider returned data that could not be accepted."
        return "The provider request failed."
