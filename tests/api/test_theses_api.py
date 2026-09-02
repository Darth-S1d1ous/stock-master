import unittest
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from pydantic import SecretStr

from app.api.dependencies import (
    ApiSecuritySettings,
    get_api_security_settings,
    get_thesis_monitoring_service,
    get_thesis_repository,
)
from app.database.thesis_repositories import ThesisRepository
from app.domain.thesis_models import InvestmentThesis, ThesisCondition
from app.main import app
from app.services.thesis_monitoring_service import (
    ThesisMonitoringResult,
    ThesisMonitoringService,
)

_USER_ID = uuid4()
_TOKEN = "test-token-with-at-least-thirty-two-characters"
_NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class ThesesApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository_mock = AsyncMock(spec=ThesisRepository)
        self.service_mock = AsyncMock(spec=ThesisMonitoringService)
        self.repository = cast(ThesisRepository, self.repository_mock)
        self.service = cast(ThesisMonitoringService, self.service_mock)

        app.dependency_overrides[get_api_security_settings] = (
            self._security_settings
        )
        app.dependency_overrides[get_thesis_repository] = (
            lambda: self.repository
        )
        app.dependency_overrides[get_thesis_monitoring_service] = (
            lambda: self.service
        )

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_authentication_is_required(self) -> None:
        response = await self.client.get("/api/v1/theses")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self._json_object(response),
            {
                "code": "authentication_required",
                "message": (
                    "Valid authentication credentials are required."
                ),
            },
        )
        self.assertEqual(
            response.headers.get("www-authenticate"),
            "Bearer",
        )
        self.repository_mock.list_theses.assert_not_awaited()

    async def test_invalid_bearer_token_is_rejected(self) -> None:
        response = await self.client.get(
            "/api/v1/theses",
            headers=self._authorization("wrong-token"),
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self._json_object(response)["code"],
            "authentication_required",
        )
        self.repository_mock.list_theses.assert_not_awaited()

    async def test_create_thesis_uses_authenticated_owner(self) -> None:
        captured: list[InvestmentThesis] = []

        def create_thesis(
            thesis: InvestmentThesis,
        ) -> InvestmentThesis:
            captured.append(thesis)
            return thesis

        self.repository_mock.create_thesis.side_effect = create_thesis

        response = await self.client.post(
            "/api/v1/theses",
            headers=self._authorization(),
            json={
                "symbol": " aapl ",
                "title": "Services remain durable",
                "description": "Monitor the investment thesis.",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].user_id, _USER_ID)
        self.assertEqual(captured[0].symbol, "AAPL")

        body = self._json_object(response)
        self.assertEqual(body["symbol"], "AAPL")
        self.assertNotIn("user_id", body)
        self.assertEqual(
            response.headers.get("location"),
            f"/api/v1/theses/{captured[0].id}",
        )

    async def test_create_thesis_rejects_client_user_id(self) -> None:
        response = await self.client.post(
            "/api/v1/theses",
            headers=self._authorization(),
            json={
                "user_id": str(uuid4()),
                "symbol": "AAPL",
                "title": "Services remain durable",
                "description": "Monitor the investment thesis.",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self._json_object(response)["code"],
            "request_validation_failed",
        )
        self.repository_mock.create_thesis.assert_not_awaited()

    async def test_list_theses_forwards_owned_filters(self) -> None:
        thesis = self._thesis()
        self.repository_mock.list_theses.return_value = [thesis]

        response = await self.client.get(
            "/api/v1/theses",
            headers=self._authorization(),
            params={
                "symbol": "aapl",
                "status": "active",
                "limit": "20",
                "offset": "5",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_array(response)
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], str(thesis.id))
        self.repository_mock.list_theses.assert_awaited_once_with(
            user_id=_USER_ID,
            symbol="aapl",
            status=thesis.status,
            limit=20,
            offset=5,
        )

    async def test_missing_thesis_returns_stable_404(self) -> None:
        thesis_id = uuid4()
        self.repository_mock.get_thesis.return_value = None

        response = await self.client.get(
            f"/api/v1/theses/{thesis_id}",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self._json_object(response),
            {
                "code": "thesis_not_found",
                "message": "The investment thesis was not found.",
            },
        )
        self.repository_mock.get_thesis.assert_awaited_once_with(
            user_id=_USER_ID,
            thesis_id=thesis_id,
        )

    async def test_create_condition_uses_path_thesis_and_owner(self) -> None:
        thesis_id = uuid4()
        captured: list[ThesisCondition] = []

        def create_condition(
            condition: ThesisCondition,
        ) -> ThesisCondition:
            captured.append(condition)
            return condition

        self.repository_mock.create_condition.side_effect = create_condition

        response = await self.client.post(
            f"/api/v1/theses/{thesis_id}/conditions",
            headers=self._authorization(),
            json={
                "name": "Daily decline",
                "kind": "risk",
                "metric": "daily_price_change_percent",
                "operator": "less_than_or_equal",
                "threshold": "-5",
                "consecutive_periods": 1,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].user_id, _USER_ID)
        self.assertEqual(captured[0].thesis_id, thesis_id)
        self.assertEqual(captured[0].threshold, Decimal(-5))
        self.assertEqual(
            response.headers.get("location"),
            (
                f"/api/v1/theses/{thesis_id}/conditions/"
                f"{captured[0].id}"
            ),
        )

    async def test_evaluate_thesis_forwards_trusted_identity(self) -> None:
        thesis = self._thesis()
        monitoring_result = ThesisMonitoringResult(
            thesis=thesis,
            source="alpha_vantage",
            started_at=_NOW,
            completed_at=_NOW,
            conditions=(),
        )
        self.service_mock.evaluate_thesis.return_value = monitoring_result

        response = await self.client.post(
            f"/api/v1/theses/{thesis.id}/evaluate",
            headers=self._authorization(),
            json={
                "source": "alpha_vantage",
                "adjustment": "raw",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_object(response)
        self.assertEqual(body["source"], "alpha_vantage")
        self.assertEqual(body["evaluation_count"], 0)
        self.assertEqual(body["matched_count"], 0)
        self.assertEqual(body["event_count"], 0)
        self.assertNotIn("user_id", cast(dict[str, Any], body["thesis"]))
        self.service_mock.evaluate_thesis.assert_awaited_once()

        call = self.service_mock.evaluate_thesis.await_args
        self.assertIsNotNone(call)
        self.assertEqual(call.kwargs["user_id"], _USER_ID)
        self.assertEqual(call.kwargs["thesis_id"], thesis.id)
        self.assertEqual(call.kwargs["source"], "alpha_vantage")

    @staticmethod
    def _security_settings() -> ApiSecuritySettings:
        return ApiSecuritySettings(
            api_user_id=_USER_ID,
            api_bearer_token=SecretStr(_TOKEN),
        )

    @staticmethod
    def _authorization(
        token: str = _TOKEN,
    ) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
        }

    @staticmethod
    def _json_object(
        response: httpx.Response,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], response.json())

    @staticmethod
    def _json_array(
        response: httpx.Response,
    ) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], response.json())

    @staticmethod
    def _thesis() -> InvestmentThesis:
        return InvestmentThesis(
            user_id=_USER_ID,
            symbol="AAPL",
            title="Services remain durable",
            description="Monitor the investment thesis.",
            created_at=_NOW,
            updated_at=_NOW,
        )


if __name__ == "__main__":
    unittest.main()
