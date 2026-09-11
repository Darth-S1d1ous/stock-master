import unittest
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
from pydantic import SecretStr

from app.agents.llm import AgentLlmRequestError, AgentLlmResponseError
from app.agents.orchestrator import AgentTurnResult, ConditionAuthorOrchestrator
from app.api.dependencies import (
    ApiSecuritySettings,
    get_agent_repository,
    get_api_security_settings,
    get_condition_author_orchestrator,
    get_thesis_repository,
)
from app.database.agent_repositories import AgentRepository
from app.database.thesis_repositories import (
    InvalidAggregateError,
    RepositoryConflictError,
    ResourceNotFoundError,
    ThesisRepository,
)
from app.domain.agent_models import (
    AgentMessage,
    AgentMessageRole,
    AgentSession,
    AgentSessionStatus,
)
from app.domain.thesis_models import InvestmentThesis
from app.main import app

_USER_ID = uuid4()
_TOKEN = "test-token-with-at-least-thirty-two-characters"
_NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


class AgentsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.thesis_repository_mock = AsyncMock(spec=ThesisRepository)
        self.agent_repository_mock = AsyncMock(spec=AgentRepository)
        self.orchestrator_mock = AsyncMock(spec=ConditionAuthorOrchestrator)
        self.thesis_repository = cast(
            ThesisRepository,
            self.thesis_repository_mock,
        )
        self.agent_repository = cast(
            AgentRepository,
            self.agent_repository_mock,
        )
        self.orchestrator = cast(
            ConditionAuthorOrchestrator,
            self.orchestrator_mock,
        )

        app.dependency_overrides[get_api_security_settings] = (
            self._security_settings
        )
        app.dependency_overrides[get_thesis_repository] = (
            lambda: self.thesis_repository
        )
        app.dependency_overrides[get_agent_repository] = (
            lambda: self.agent_repository
        )
        app.dependency_overrides[get_condition_author_orchestrator] = (
            lambda: self.orchestrator
        )

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()

    async def test_authentication_is_required(self) -> None:
        thesis_id = uuid4()

        response = await self.client.post(
            f"/api/v1/theses/{thesis_id}/agent/sessions",
        )

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
        self.agent_repository_mock.create_session.assert_not_awaited()

    async def test_create_session_uses_authenticated_owner(self) -> None:
        thesis = self._thesis()
        captured: list[AgentSession] = []

        self.thesis_repository_mock.require_thesis.return_value = thesis

        def create_session(session: AgentSession) -> AgentSession:
            captured.append(session)
            return session

        self.agent_repository_mock.create_session.side_effect = create_session

        response = await self.client.post(
            f"/api/v1/theses/{thesis.id}/agent/sessions",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].user_id, _USER_ID)
        self.assertEqual(captured[0].thesis_id, thesis.id)
        self.assertEqual(captured[0].symbol, "AAPL")
        self.assertEqual(captured[0].status, AgentSessionStatus.OPEN)

        body = self._json_object(response)
        self.assertEqual(body["symbol"], "AAPL")
        self.assertEqual(body["status"], "open")
        self.assertNotIn("user_id", body)
        self.assertEqual(
            response.headers.get("location"),
            f"/api/v1/agent/sessions/{captured[0].id}",
        )
        self.thesis_repository_mock.require_thesis.assert_awaited_once_with(
            _USER_ID,
            thesis.id,
        )

    async def test_missing_thesis_returns_stable_404(self) -> None:
        thesis_id = uuid4()
        self.thesis_repository_mock.require_thesis.side_effect = (
            ResourceNotFoundError("Investment thesis not found or inaccessible")
        )

        response = await self.client.post(
            f"/api/v1/theses/{thesis_id}/agent/sessions",
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
        self.agent_repository_mock.create_session.assert_not_awaited()

    async def test_existing_open_session_returns_conflict(self) -> None:
        thesis = self._thesis()
        self.thesis_repository_mock.require_thesis.return_value = thesis
        self.agent_repository_mock.create_session.side_effect = (
            RepositoryConflictError("An open session already exists for this thesis")
        )

        response = await self.client.post(
            f"/api/v1/theses/{thesis.id}/agent/sessions",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self._json_object(response)["code"],
            "agent_session_conflict",
        )

    async def test_get_open_session_returns_current(self) -> None:
        thesis = self._thesis()
        session = self._session(thesis_id=thesis.id)
        self.thesis_repository_mock.require_thesis.return_value = thesis
        self.agent_repository_mock.get_open_session.return_value = session

        response = await self.client.get(
            f"/api/v1/theses/{thesis.id}/agent/sessions/open",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_object(response)
        self.assertEqual(body["id"], str(session.id))
        self.assertNotIn("user_id", body)
        self.agent_repository_mock.get_open_session.assert_awaited_once_with(
            _USER_ID,
            thesis.id,
        )

    async def test_missing_open_session_returns_stable_404(self) -> None:
        thesis = self._thesis()
        self.thesis_repository_mock.require_thesis.return_value = thesis
        self.agent_repository_mock.get_open_session.return_value = None

        response = await self.client.get(
            f"/api/v1/theses/{thesis.id}/agent/sessions/open",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self._json_object(response),
            {
                "code": "agent_session_not_found",
                "message": "The agent session was not found.",
            },
        )

    async def test_list_messages_forwards_owned_filters(self) -> None:
        session = self._session()
        message = AgentMessage(
            session_id=session.id,
            user_id=_USER_ID,
            role=AgentMessageRole.USER,
            content="Add a risk rule for a 5% daily drop.",
            created_at=_NOW,
        )
        self.agent_repository_mock.list_messages.return_value = [message]

        response = await self.client.get(
            f"/api/v1/agent/sessions/{session.id}/messages",
            headers=self._authorization(),
            params={"limit": "20", "offset": "5"},
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_array(response)
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["role"], "user")
        self.assertEqual(body[0]["content"], message.content)
        self.assertNotIn("user_id", body[0])
        self.agent_repository_mock.list_messages.assert_awaited_once_with(
            user_id=_USER_ID,
            session_id=session.id,
            limit=20,
            offset=5,
        )

    async def test_generate_forwards_trusted_identity(self) -> None:
        session = self._session()
        self.orchestrator_mock.generate.return_value = AgentTurnResult(
            assistant_text="Drafted conditions from the catalog.",
            round_count=2,
            stop_reason="completed",
            session_id=session.id,
        )

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session.id}/generate",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_object(response)
        self.assertEqual(body["assistant_text"], "Drafted conditions from the catalog.")
        self.assertEqual(body["round_count"], 2)
        self.assertEqual(body["stop_reason"], "completed")
        self.assertEqual(body["session_id"], str(session.id))
        self.orchestrator_mock.generate.assert_awaited_once_with(
            user_id=_USER_ID,
            session_id=session.id,
        )

    async def test_chat_forwards_user_message(self) -> None:
        session = self._session()
        self.orchestrator_mock.chat.return_value = AgentTurnResult(
            assistant_text="I created a risk condition.",
            round_count=3,
            stop_reason="completed",
            session_id=session.id,
        )

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session.id}/chat",
            headers=self._authorization(),
            json={"message": "Add a risk rule for a 5% daily drop."},
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_object(response)
        self.assertEqual(body["assistant_text"], "I created a risk condition.")
        self.orchestrator_mock.chat.assert_awaited_once_with(
            user_id=_USER_ID,
            session_id=session.id,
            user_text="Add a risk rule for a 5% daily drop.",
        )

    async def test_chat_rejects_client_user_id(self) -> None:
        session_id = uuid4()

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session_id}/chat",
            headers=self._authorization(),
            json={
                "message": "Add a risk rule.",
                "user_id": str(uuid4()),
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self._json_object(response)["code"],
            "request_validation_failed",
        )
        self.orchestrator_mock.chat.assert_not_awaited()

    async def test_chat_rejects_empty_message(self) -> None:
        session_id = uuid4()

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session_id}/chat",
            headers=self._authorization(),
            json={"message": "   "},
        )

        self.assertEqual(response.status_code, 422)
        self.orchestrator_mock.chat.assert_not_awaited()

    async def test_closed_session_returns_conflict(self) -> None:
        session_id = uuid4()
        self.orchestrator_mock.chat.side_effect = InvalidAggregateError(
            "Cannot run the agent on a closed session"
        )

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session_id}/chat",
            headers=self._authorization(),
            json={"message": "Add a risk rule."},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self._json_object(response),
            {
                "code": "agent_session_closed",
                "message": "The agent session is closed.",
            },
        )

    async def test_llm_request_error_returns_bad_gateway(self) -> None:
        session_id = uuid4()
        self.orchestrator_mock.generate.side_effect = AgentLlmRequestError(
            "LLM provider request failed"
        )

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session_id}/generate",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self._json_object(response)["code"],
            "agent_llm_unreachable",
        )

    async def test_llm_response_error_returns_bad_gateway(self) -> None:
        session_id = uuid4()
        self.orchestrator_mock.generate.side_effect = AgentLlmResponseError(
            "LLM provider returned an error status"
        )

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session_id}/generate",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            self._json_object(response)["code"],
            "agent_llm_invalid_response",
        )

    async def test_close_session_forwards_identity(self) -> None:
        session = self._session()
        closed = session.model_copy(
            update={
                "status": AgentSessionStatus.CLOSED,
                "updated_at": _NOW,
            }
        )
        self.agent_repository_mock.close_session.return_value = closed

        response = await self.client.post(
            f"/api/v1/agent/sessions/{session.id}/close",
            headers=self._authorization(),
        )

        self.assertEqual(response.status_code, 200)
        body = self._json_object(response)
        self.assertEqual(body["status"], "closed")
        self.assertNotIn("user_id", body)
        self.agent_repository_mock.close_session.assert_awaited_once_with(
            user_id=_USER_ID,
            session_id=session.id,
        )

    @staticmethod
    def _security_settings() -> ApiSecuritySettings:
        return ApiSecuritySettings(
            api_user_id=_USER_ID,
            api_bearer_token=SecretStr(_TOKEN),
        )

    @staticmethod
    def _authorization(token: str = _TOKEN) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        return cast(dict[str, Any], response.json())

    @staticmethod
    def _json_array(response: httpx.Response) -> list[dict[str, Any]]:
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

    @staticmethod
    def _session(*, thesis_id: Any = None) -> AgentSession:
        return AgentSession(
            user_id=_USER_ID,
            thesis_id=thesis_id or uuid4(),
            symbol="AAPL",
            created_at=_NOW,
            updated_at=_NOW,
        )


if __name__ == "__main__":
    unittest.main()
