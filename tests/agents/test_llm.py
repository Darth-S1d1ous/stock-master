import json
import unittest

import httpx
from pydantic import ValidationError

from app.agents.llm import (
    AgentLlmResponseError,
    AgentLlmSettings,
    LlmChatMessage,
    OpenAICompatibleLlmClient,
)
from app.agents.tools import TOOL_DEFINITIONS


def _settings() -> AgentLlmSettings:
    return AgentLlmSettings(
        agent_llm_api_key="test-key-ok",
        agent_llm_base_url="https://api.openai.com/v1",
        agent_llm_model="gpt-4.1-mini",
        agent_llm_prompt_version="condition-author-v1",
    )


class AgentLlmSettingsTests(unittest.TestCase):
    def test_rejects_unapproved_urls(self) -> None:
        invalid = (
            "http://api.openai.com/v1",
            "https://127.0.0.1/v1",
            "https://api.openai.com/v1?steal=1",
            "https://user:pass@api.openai.com/v1",
            "https://evil.example/v1",
        )
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    AgentLlmSettings(
                        agent_llm_api_key="test-key-ok",
                        agent_llm_base_url=url,
                    )

    def test_api_key_is_redacted(self) -> None:
        settings = AgentLlmSettings(agent_llm_api_key="super-secret-key")
        self.assertNotIn("super-secret-key", repr(settings))


class OpenAICompatibleLlmClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_tool_calls_and_does_not_follow_redirects(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/redirect"):
                return httpx.Response(
                    302,
                    headers={"Location": "https://evil.example/leak"},
                    request=request,
                )
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gpt-4.1-mini")
            self.assertEqual(body["tools"], list(TOOL_DEFINITIONS))
            self.assertEqual(
                request.headers["authorization"],
                "Bearer test-key-ok",
            )
            return httpx.Response(
                200,
                json={
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "create_condition",
                                            "arguments": json.dumps(
                                                {
                                                    "name": "PE spike",
                                                    "kind": "risk",
                                                    "metric": "pe_ratio_change_percent",
                                                    "operator": "greater_than",
                                                    "threshold": 20,
                                                }
                                            ),
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
                request=request,
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
        ) as http_client:
            client = OpenAICompatibleLlmClient(
                settings=_settings(),
                http_client=http_client,
            )
            completion = await client.complete(
                messages=[
                    LlmChatMessage(role="user", content="Generate conditions"),
                ],
                tools=TOOL_DEFINITIONS,
            )

        self.assertEqual(len(completion.tool_calls), 1)
        self.assertEqual(completion.tool_calls[0].name, "create_condition")
        self.assertEqual(completion.tool_calls[0].arguments["threshold"], 20)
        self.assertEqual(completion.prompt_version, "condition-author-v1")
        self.assertEqual(len(requests), 1)

    async def test_rejects_non_object_tool_arguments(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "create_condition",
                                            "arguments": "[1, 2]",
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                },
                request=request,
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
        ) as http_client:
            client = OpenAICompatibleLlmClient(
                settings=_settings(),
                http_client=http_client,
            )
            with self.assertRaises(AgentLlmResponseError):
                await client.complete(
                    messages=[LlmChatMessage(role="user", content="Go")],
                    tools=TOOL_DEFINITIONS,
                )