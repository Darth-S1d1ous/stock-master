import unittest
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from pydantic import SecretStr

from app.api.dependencies import (
    ApiSecuritySettings,
    get_api_security_settings,
    get_thesis_repository,
)
from app.database.thesis_repositories import RepositoryConflictError, ThesisRepository
from app.domain.thesis_models import (
    ComparisonOperator,
    ConditionKind,
    InvestmentThesis,
    MetricCode,
    ThesisCondition,
)
from app.main import app

_USER_ID = uuid4()
_TOKEN = "test-token-with-at-least-thirty-two-characters"
_NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class LifecycleApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository_mock = AsyncMock(spec=ThesisRepository)
        self.repository = cast(ThesisRepository, self.repository_mock)
        app.dependency_overrides[get_api_security_settings] = self._security_settings
        app.dependency_overrides[get_thesis_repository] = lambda: self.repository
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_update_thesis_uses_optimistic_version(self) -> None:
        thesis = self._thesis().model_copy(
            update={"title": "Updated title", "version": 2}
        )
        self.repository_mock.update_thesis.return_value = thesis
        response = await self.client.patch(
            f"/api/v1/theses/{thesis.id}",
            headers=self._authorization(),
            json={"expected_version": 1, "title": "Updated title"},
        )
        self.assertEqual(response.status_code, 200)
        self.repository_mock.update_thesis.assert_awaited_once_with(
            user_id=_USER_ID,
            thesis_id=thesis.id,
            expected_version=1,
            title="Updated title",
            description=None,
            status=None,
            reason=None,
        )

    async def test_version_conflict_has_stable_error(self) -> None:
        thesis = self._thesis()
        self.repository_mock.update_thesis.side_effect = RepositoryConflictError()
        response = await self.client.patch(
            f"/api/v1/theses/{thesis.id}",
            headers=self._authorization(),
            json={"expected_version": 1, "title": "Updated title"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "thesis_version_conflict")

    async def test_condition_enabled_change_creates_versioned_update(self) -> None:
        condition = self._condition().model_copy(
            update={"enabled": False, "version": 2}
        )
        self.repository_mock.update_condition.return_value = condition
        response = await self.client.patch(
            f"/api/v1/theses/{condition.thesis_id}/conditions/{condition.id}",
            headers=self._authorization(),
            json={"expected_version": 1, "enabled": False},
        )
        self.assertEqual(response.status_code, 200)
        self.repository_mock.update_condition.assert_awaited_once_with(
            user_id=_USER_ID,
            thesis_id=condition.thesis_id,
            condition_id=condition.id,
            expected_version=1,
            changes={"enabled": False},
        )

    @staticmethod
    def _thesis() -> InvestmentThesis:
        return InvestmentThesis(
            user_id=_USER_ID,
            symbol="AAPL",
            title="Original title",
            description="Original description.",
            created_at=_NOW,
            updated_at=_NOW,
        )

    @classmethod
    def _condition(cls) -> ThesisCondition:
        thesis = cls._thesis()
        return ThesisCondition(
            thesis_id=thesis.id,
            user_id=_USER_ID,
            name="Daily decline",
            kind=ConditionKind.RISK,
            metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
            operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            threshold=Decimal(-5),
            created_at=_NOW,
            updated_at=_NOW,
        )

    @staticmethod
    def _security_settings() -> ApiSecuritySettings:
        return ApiSecuritySettings(
            api_user_id=_USER_ID,
            api_bearer_token=SecretStr(_TOKEN),
        )

    @staticmethod
    def _authorization() -> dict[str, str]:
        return {"Authorization": f"Bearer {_TOKEN}"}


if __name__ == "__main__":
    unittest.main()
