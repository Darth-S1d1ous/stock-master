import json
import unittest

import httpx
from pydantic import ValidationError

from app.agents.llm import (
    LLM_PROVIDERS,
    AgentLlmProvider,
    AgentLlmResponseError,
    AgentLlmSettings,
    LlmChatMessage,
    LlmProviderSpec,
    OpenAICompatibleLlmClient,
    register_llm_provider,
    registered_llm_providers,
)
from app.agents.tools import TOOL_DEFINITIONS


def _settings(**overrides: object) -> AgentLlmSettings:
    values: dict[str, object] = {
        "agent_llm_provider": "openai",
        "agent_llm_api_key": "test-key-ok",
        "agent_llm_base_url": "https://api.openai.com/v1",
        "agent_llm_model": "gpt-4.1-mini",
        "agent_llm_timeout_seconds": 5.0,
        "agent_llm_prompt_version": "condition-author-v1",
    }
    values.update(overrides)
    return AgentLlmSettings.model_validate(values)


class AgentLlmSettingsTests(unittest.TestCase):
    def test_rejects_unapproved_urls(self) -> None:
        invalid = (
            "http://api.openai.com/v1",
            "https://127.0.0.1/v1",
            "https://api.openai.com/v1?steal=1",
            "https://user:pass@api.openai.com/v1",
            "https://evil.example/v1",
            "https://integrate.api.nvidia.com/v1",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                _settings(agent_llm_base_url=url)

    def test_api_key_is_redacted(self) -> None:
        settings = _settings(agent_llm_api_key="super-secret-key")
        self.assertNotIn("super-secret-key", repr(settings))

    def test_nvidia_defaults_host_and_model(self) -> None:
        settings = AgentLlmSettings.model_validate(
            {
                "agent_llm_provider": "nvidia",
                "agent_llm_nvidia_api_key": "nvapi-test-key",
            }
        )
        spec = LLM_PROVIDERS[AgentLlmProvider.NVIDIA]
        self.assertEqual(settings.base_url, spec.base_url)
        self.assertEqual(settings.model, spec.default_model)
        self.assertEqual(settings.resolved_api_key(), "nvapi-test-key")

    def test_rejects_openai_host_for_nvidia_provider(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(
                agent_llm_provider="nvidia",
                agent_llm_nvidia_api_key="nvapi-test-key",
                agent_llm_base_url="https://api.openai.com/v1",
            )

    def test_provider_key_is_preferred_over_shared_key(self) -> None:
        settings = _settings(
            agent_llm_provider="nvidia",
            agent_llm_api_key="shared-key",
            agent_llm_nvidia_api_key="nvapi-preferred",
            agent_llm_base_url="https://integrate.api.nvidia.com/v1",
            agent_llm_model="nvidia/nemotron-3.5-lightning-30b-a3b",
        )
        self.assertEqual(settings.resolved_api_key(), "nvapi-preferred")

    def test_rejects_missing_api_key(self) -> None:
        with self.assertRaises(ValidationError):
            AgentLlmSettings.model_validate({"agent_llm_provider": "openai"})

    def test_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValidationError):
            _settings(agent_llm_provider="cursor")

    def test_openai_provider_key_is_preferred_over_shared_key(self) -> None:
        settings = _settings(
            agent_llm_openai_api_key="openai-preferred",
            agent_llm_api_key="shared-key",
        )
        self.assertEqual(settings.resolved_api_key(), "openai-preferred")

    def test_key_resolution_is_driven_by_provider_spec(self) -> None:
        settings = _settings(
            agent_llm_openai_api_key="openai-key",
            agent_llm_nvidia_api_key="nvidia-key",
            agent_llm_api_key="shared-key",
        )
        openai_spec = LLM_PROVIDERS[AgentLlmProvider.OPENAI]
        nvidia_spec = LLM_PROVIDERS[AgentLlmProvider.NVIDIA]
        self.assertEqual(openai_spec.api_key_from(settings), "openai-key")
        self.assertEqual(nvidia_spec.api_key_from(settings), "nvidia-key")

    def test_builtin_providers_are_registered(self) -> None:
        self.assertEqual(
            set(registered_llm_providers()),
            {AgentLlmProvider.OPENAI, AgentLlmProvider.NVIDIA},
        )

    def test_register_llm_provider_extends_key_resolution(self) -> None:
        original = LLM_PROVIDERS[AgentLlmProvider.OPENAI]
        register_llm_provider(
            AgentLlmProvider.OPENAI,
            LlmProviderSpec(
                host=original.host,
                base_url=original.base_url,
                default_model=original.default_model,
                api_key_attr="agent_llm_nvidia_api_key",
            ),
        )
        try:
            settings = _settings(
                agent_llm_openai_api_key="openai-key",
                agent_llm_nvidia_api_key="nvidia-as-openai",
            )
            self.assertEqual(settings.resolved_api_key(), "nvidia-as-openai")
        finally:
            register_llm_provider(AgentLlmProvider.OPENAI, original)


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
            self.assertEqual(body["max_tokens"], 4096)
            self.assertEqual(body["tools"], list(TOOL_DEFINITIONS))
            self.assertEqual(
                request.headers["authorization"],
                "Bearer test-key-ok",
            )
            self.assertEqual(request.headers["user-agent"], "stock-master-bot/0.1")
            self.assertEqual(
                str(request.url),
                "https://api.openai.com/v1/chat/completions",
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

    async def test_posts_to_nvidia_host_with_provider_key(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            body = json.loads(request.content)
            self.assertEqual(
                body["model"],
                "nvidia/nemotron-3.5-lightning-30b-a3b",
            )
            self.assertEqual(
                str(request.url),
                "https://integrate.api.nvidia.com/v1/chat/completions",
            )
            self.assertEqual(
                request.headers["authorization"],
                "Bearer nvapi-test-key",
            )
            return httpx.Response(
                200,
                json={
                    "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "pong"},
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
                settings=AgentLlmSettings.model_validate(
                    {
                        "agent_llm_provider": "nvidia",
                        "agent_llm_nvidia_api_key": "nvapi-test-key",
                    }
                ),
                http_client=http_client,
            )
            completion = await client.complete(
                messages=[LlmChatMessage(role="user", content="ping")],
                tools=(),
            )

        self.assertEqual(completion.content, "pong")
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
