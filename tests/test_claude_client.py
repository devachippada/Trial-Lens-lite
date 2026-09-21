"""Tests for the Claude Messages API wrapper (app/generation/client.py).

`AnthropicClaudeClient` takes an already-constructed SDK client, so its
response-parsing logic is tested here with a plain fake object — no
`anthropic` package needs to be installed, and no network call is made.
"""

from types import SimpleNamespace

import pytest

from app.generation.client import AnthropicClaudeClient, ClaudeResponse, get_claude_client


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


class TestAnthropicClaudeClient:
    def test_extracts_text_from_a_single_text_block(self):
        fake = _FakeAnthropicClient(SimpleNamespace(content=[_text_block("hello world")]))
        client = AnthropicClaudeClient(client=fake, model="claude-sonnet-4-5")

        result = client.complete(system="sys", user="usr", max_tokens=256)

        assert result == ClaudeResponse(text="hello world")

    def test_concatenates_multiple_text_blocks(self):
        fake = _FakeAnthropicClient(
            SimpleNamespace(content=[_text_block("part one "), _text_block("part two")])
        )
        client = AnthropicClaudeClient(client=fake, model="claude-sonnet-4-5")

        result = client.complete(system="sys", user="usr", max_tokens=256)

        assert result.text == "part one part two"

    def test_ignores_non_text_blocks(self):
        tool_block = SimpleNamespace(type="tool_use", text=None)
        fake = _FakeAnthropicClient(SimpleNamespace(content=[tool_block, _text_block("actual answer")]))
        client = AnthropicClaudeClient(client=fake, model="claude-sonnet-4-5")

        result = client.complete(system="sys", user="usr", max_tokens=256)

        assert result.text == "actual answer"

    def test_passes_model_system_user_and_max_tokens_through(self):
        fake = _FakeAnthropicClient(SimpleNamespace(content=[_text_block("ok")]))
        client = AnthropicClaudeClient(client=fake, model="claude-sonnet-4-5")

        client.complete(system="be helpful", user="what is X", max_tokens=512)

        [call] = fake.messages.calls
        assert call["model"] == "claude-sonnet-4-5"
        assert call["system"] == "be helpful"
        assert call["max_tokens"] == 512
        assert call["messages"] == [{"role": "user", "content": "what is X"}]


class TestGetClaudeClientFactory:
    def test_raises_without_an_api_key(self):
        settings = SimpleNamespace(anthropic_api_key=None, anthropic_model="claude-sonnet-4-5")

        with pytest.raises(RuntimeError):
            get_claude_client(settings)

    def test_raises_on_empty_string_api_key_too(self):
        settings = SimpleNamespace(anthropic_api_key="", anthropic_model="claude-sonnet-4-5")

        with pytest.raises(RuntimeError):
            get_claude_client(settings)


class TestGetClaudeClientFactoryWithRealSdk:
    def test_constructs_an_anthropic_backed_client(self):
        # Only runs where the `anthropic` package is actually installed
        # (it isn't in this project's sandbox — see docs/phase-4-notes.md).
        pytest.importorskip("anthropic")
        settings = SimpleNamespace(anthropic_api_key="test-key", anthropic_model="claude-sonnet-4-5")

        client = get_claude_client(settings)

        assert isinstance(client, AnthropicClaudeClient)
