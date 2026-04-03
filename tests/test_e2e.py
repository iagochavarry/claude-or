"""End-to-end tests — real requests through OpenRouter and through the proxy.

These tests hit the live OpenRouter API and measure latency.
They require OPENROUTER_API_KEY to be set (via .env or environment).

Run:
    pytest tests/test_e2e.py -v
"""

import os
import subprocess
import sys
import time

import pytest
import requests

from claude_or.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    generate_config_yaml,
    get_model_mapping,
    get_port,
    get_provider_config,
    load_env,
)
from claude_or.cli import _wait_for_port

# ── Setup ───────────────────────────────────────────────────────────────

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_LATENCY_SECONDS = 30


@pytest.fixture(scope="module", autouse=True)
def _load_env():
    """Load .env once for the whole module."""
    load_env()


@pytest.fixture(scope="module")
def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.fail("OPENROUTER_API_KEY is required for e2e tests")
    return key


@pytest.fixture(scope="module")
def provider():
    return get_provider_config()


def _chat(api_key, model, prompt, provider=None, max_tokens=100):
    """Send a chat completion request to OpenRouter. Returns (response_dict, elapsed_seconds)."""
    body = {
        "model": model.removeprefix("openrouter/"),
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if provider:
        body["provider"] = {"order": [provider], "allow_fallbacks": True}

    start = time.time()
    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=MAX_LATENCY_SECONDS,
    )
    elapsed = time.time() - start
    resp.raise_for_status()
    return resp.json(), elapsed


def _extract_content(data):
    """Extract text content from OpenRouter response."""
    choices = data.get("choices", [])
    if not choices:
        return ""
    msg = choices[0].get("message", {})
    return msg.get("content") or msg.get("reasoning") or ""


# ── Tests: Basic connectivity ───────────────────────────────────────────


class TestOpenRouterConnectivity:
    """AC: We can reach OpenRouter and get a response from the default model."""

    def test_default_model_responds(self, api_key, provider):
        data, elapsed = _chat(api_key, DEFAULT_MODEL, "Reply with the word 'pong'.", provider)
        content = _extract_content(data)
        assert content, f"Empty response from {DEFAULT_MODEL}"
        print(f"\n  Model: {DEFAULT_MODEL} via {provider} — {elapsed:.1f}s")
        print(f"  Response: {content[:100]}")

    def test_response_under_max_latency(self, api_key, provider):
        _, elapsed = _chat(api_key, DEFAULT_MODEL, "Say ok.", provider, max_tokens=10)
        assert elapsed < MAX_LATENCY_SECONDS, f"Request took {elapsed:.1f}s (max {MAX_LATENCY_SECONDS}s)"


# ── Tests: Correctness ─────────────────────────────────────────────────


class TestModelCorrectness:
    """AC: The model gives correct answers to simple questions."""

    def test_arithmetic(self, api_key, provider):
        data, elapsed = _chat(
            api_key, DEFAULT_MODEL,
            "What is 2+2? Reply with ONLY the number, nothing else.",
            provider, max_tokens=50,
        )
        content = _extract_content(data).strip()
        print(f"\n  Arithmetic: '{content}' in {elapsed:.1f}s")
        assert "4" in content

    def test_factual_knowledge(self, api_key, provider):
        data, elapsed = _chat(
            api_key, DEFAULT_MODEL,
            "What is the capital of France? Reply with ONLY the city name.",
            provider, max_tokens=50,
        )
        content = _extract_content(data).strip()
        print(f"\n  Factual: '{content}' in {elapsed:.1f}s")
        assert "paris" in content.lower()

    def test_instruction_following(self, api_key, provider):
        data, elapsed = _chat(
            api_key, DEFAULT_MODEL,
            "List exactly 3 colors, one per line. No numbering, no extra text.",
            provider, max_tokens=200,
        )
        content = _extract_content(data).strip()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        print(f"\n  Instruction following: {lines} in {elapsed:.1f}s")
        assert len(lines) >= 3, f"Expected 3 lines, got {len(lines)}: {content}"


# ── Tests: Latency benchmarks ──────────────────────────────────────────


class TestLatencyBenchmarks:
    """AC: Measure and report latency for each available provider."""

    PROVIDERS_TO_TEST = ["Fireworks", "Together", "Novita"]

    @pytest.mark.parametrize("test_provider", PROVIDERS_TO_TEST)
    def test_provider_latency(self, api_key, test_provider):
        try:
            data, elapsed = _chat(
                api_key, DEFAULT_MODEL,
                "What is 2+2? Reply with ONLY the number.",
                test_provider, max_tokens=50,
            )
            content = _extract_content(data).strip()
            actual_provider = data.get("provider", "unknown")
            print(f"\n  {test_provider} ({actual_provider}): '{content}' in {elapsed:.1f}s")
            assert elapsed < MAX_LATENCY_SECONDS
        except (requests.exceptions.RequestException, KeyError) as e:
            pytest.skip(f"{test_provider} unavailable: {e}")


# ── Tests: Full proxy e2e ───────────────────────────────────────────────

PROXY_PORT = 4111  # Use a non-default port to avoid conflicts


class TestProxyE2E:
    """AC: Requests through the proxy with Claude model names route to Kimi K2.5."""

    @pytest.fixture(scope="class", autouse=True)
    def proxy(self):
        """Start the LiteLLM proxy as a subprocess for the test class."""
        load_env()
        config_path = generate_config_yaml()
        assert config_path, "Failed to generate config (is OPENROUTER_API_KEY set?)"

        proc = subprocess.Popen(
            [sys.executable, "-m", "litellm.proxy.proxy_cli",
             "--config", config_path, "--host", "127.0.0.1", "--port", str(PROXY_PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not _wait_for_port(PROXY_PORT, timeout=30):
            proc.kill()
            pytest.fail(f"Proxy failed to start on port {PROXY_PORT}")

        yield proc

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            os.unlink(config_path)
        except OSError:
            pass

    def _proxy_chat(self, model, prompt, max_tokens=100):
        """Send an Anthropic Messages API request through the proxy."""
        start = time.time()
        resp = requests.post(
            f"http://localhost:{PROXY_PORT}/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": "sk-placeholder",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=MAX_LATENCY_SECONDS,
        )
        elapsed = time.time() - start
        resp.raise_for_status()
        return resp.json(), elapsed

    def _extract_proxy_content(self, data):
        """Extract text from Anthropic Messages API response."""
        for block in data.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                return block["text"]
            if block.get("type") == "thinking" and block.get("thinking"):
                return block["thinking"]
        return ""

    def test_sonnet_routes_through_proxy(self, proxy):
        data, elapsed = self._proxy_chat(
            "claude-sonnet-4-6",
            "What is 2+2? Reply with ONLY the number.",
            max_tokens=100,
        )
        content = self._extract_proxy_content(data)
        print(f"\n  Proxy sonnet: '{content[:80]}' in {elapsed:.1f}s")
        assert content, "Empty response from proxy"
        assert "4" in content

    def test_opus_routes_through_proxy(self, proxy):
        data, elapsed = self._proxy_chat(
            "claude-opus-4-6",
            "What is 3+3? Reply with ONLY the number.",
            max_tokens=100,
        )
        content = self._extract_proxy_content(data)
        print(f"\n  Proxy opus: '{content[:80]}' in {elapsed:.1f}s")
        assert content, "Empty response from proxy"
        assert "6" in content

    def test_haiku_routes_through_proxy(self, proxy):
        data, elapsed = self._proxy_chat(
            "claude-haiku-4-5",
            "What is 5+5? Reply with ONLY the number.",
            max_tokens=100,
        )
        content = self._extract_proxy_content(data)
        print(f"\n  Proxy haiku: '{content[:80]}' in {elapsed:.1f}s")
        assert content, "Empty response from proxy"
        assert "10" in content

    def test_wildcard_catches_new_model_version(self, proxy):
        """A model name we never hardcoded should still route via wildcard."""
        data, elapsed = self._proxy_chat(
            "claude-sonnet-4-20250514",
            "What is 7+7? Reply with ONLY the number.",
            max_tokens=100,
        )
        content = self._extract_proxy_content(data)
        print(f"\n  Proxy wildcard: '{content[:80]}' in {elapsed:.1f}s")
        assert content, "Empty response from proxy"
        assert "14" in content

    def test_response_has_anthropic_format(self, proxy):
        data, _ = self._proxy_chat(
            "claude-sonnet-4-6",
            "Say ok.",
            max_tokens=200,
        )
        assert data.get("type") == "message"
        assert data.get("role") == "assistant"
        assert isinstance(data.get("content"), list)
        assert "stop_reason" in data
