from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from pydantic import SecretStr

from app.api.dependencies import (
    ApiSecuritySettings,
    get_api_security_settings,
    get_thesis_repository,
)
from app.database.thesis_repositories import ThesisRepository
from app.domain.event_models import (
    DomainEvent,
    EventEvidence,
    EventFeedback,
    EventSeverity,
    EventStatus,
    EvidenceType,
    FeedbackType,
)
from app.domain.thesis_models import MetricCode
from app.main import app

_USER_ID = uuid4()
_TOKEN = "test-token-with-at-least-thirty-two-characters"
_NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class EventsApiTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_event_list_forwards_owned_filters(self) -> None:
        event = self._event()
        self.repository_mock.list_events.return_value = [event]
        response = await self.client.get(
            "/api/v1/events",
            headers=self._authorization(),
            params={
                "symbol": "AAPL",
                "thesis_id": str(event.thesis_id),
                "severity": "critical",
                "status": "open",
                "occurred_from": "2026-08-01",
                "occurred_to": "2026-08-27",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._json_array(response)[0]["id"], str(event.id))
        self.repository_mock.list_events.assert_awaited_once_with(
            user_id=_USER_ID,
            thesis_id=event.thesis_id,
            symbol="AAPL",
            severity=EventSeverity.CRITICAL,
            status=EventStatus.OPEN,
            occurred_from=date(2026, 8, 1),
            occurred_to=date(2026, 8, 27),
            limit=100,
            offset=0,
        )

    async def test_evidence_query_uses_authenticated_owner(self) -> None:
        event = self._event()
        evidence = EventEvidence(
            event_id=event.id,
            user_id=_USER_ID,
            evidence_type=EvidenceType.METRIC_OBSERVATION,
            source="alpha_vantage",
            metric=MetricCode.DAILY_PRICE_CHANGE_PERCENT,
            observed_value=Decimal("-6"),
            description="Observed daily change.",
            data_as_of=event.occurred_on,
            observed_at=_NOW,
        )
        self.repository_mock.list_event_evidence.return_value = [evidence]
        response = await self.client.get(
            f"/api/v1/events/{event.id}/evidence",
            headers=self._authorization(),
        )
        self.assertEqual(response.status_code, 200)
        self.repository_mock.list_event_evidence.assert_awaited_once_with(
            user_id=_USER_ID,
            event_id=event.id,
        )

    async def test_feedback_is_appended_with_authenticated_owner(self) -> None:
        event = self._event()

        async def save_feedback(feedback: EventFeedback) -> EventFeedback:
            return feedback

        self.repository_mock.save_feedback.side_effect = save_feedback
        response = await self.client.post(
            f"/api/v1/events/{event.id}/feedback",
            headers=self._authorization(),
            json={"feedback_type": "useful", "comment": "Actionable."},
        )
        self.assertEqual(response.status_code, 201)
        body = self._json_object(response)
        self.assertEqual(body["event_id"], str(event.id))
        self.assertEqual(body["feedback_type"], FeedbackType.USEFUL.value)
        call = self.repository_mock.save_feedback.await_args
        self.assertEqual(call.args[0].user_id, _USER_ID)
        self.assertEqual(call.args[0].comment, "Actionable.")

    async def test_event_endpoints_require_authentication(self) -> None:
        response = await self.client.get("/api/v1/events")
        self.assertEqual(response.status_code, 401)
        self.repository_mock.list_events.assert_not_awaited()

    @staticmethod
    def _event() -> DomainEvent:
        return DomainEvent(
            user_id=_USER_ID,
            thesis_id=uuid4(),
            condition_id=uuid4(),
            evaluation_id=uuid4(),
            symbol="AAPL",
            event_type="invalidation_condition_matched",
            severity=EventSeverity.CRITICAL,
            title="Invalidation matched",
            summary="The deterministic invalidation condition matched.",
            occurred_on=date(2026, 8, 27),
            detected_at=_NOW,
            rule_version=1,
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

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        return cast(dict[str, Any], response.json())

    @staticmethod
    def _json_array(response: httpx.Response) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], response.json())


if __name__ == "__main__":
    unittest.main()
