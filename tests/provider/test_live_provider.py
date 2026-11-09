"""Explicit opt-in only. This test can incur provider charges when configured."""

import asyncio
import os

import pytest

from praxioj.runtime import Message, ModelConfig, OpenAICompatibleProvider, ProviderCapabilities, RuntimeContext


@pytest.mark.live_provider
@pytest.mark.skipif(
    os.environ.get("PRAXIOJ_RUN_LIVE_TESTS") != "1"
    or not all(os.environ.get(name) for name in ["PRAXIOJ_TEST_LLM_BASE_URL", "PRAXIOJ_TEST_LLM_MODEL", "PRAXIOJ_TEST_LLM_API_KEY"]),
    reason="Live provider tests require explicit opt-in and dedicated test endpoint, model and credentials",
)
def test_opt_in_live_provider_text_response():
    provider = OpenAICompatibleProvider(os.environ["PRAXIOJ_TEST_LLM_BASE_URL"], api_key=os.environ["PRAXIOJ_TEST_LLM_API_KEY"],
                                        capabilities=ProviderCapabilities(temperature=False))
    response = asyncio.run(provider.generate(
        [Message(role="user", content="Reply with a short greeting.")],
        ModelConfig(provider="compatible", model=os.environ["PRAXIOJ_TEST_LLM_MODEL"], temperature=None, max_output_tokens=32), RuntimeContext(),
    ))
    assert response.content
