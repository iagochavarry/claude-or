"""End-to-end tests — real requests through OpenRouter.

These tests hit the live OpenRouter API and measure latency.
They require OPENROUTER_API_KEY to be set (via .env or environment).

Run:
    pytest tests/test_e2e.py -v
"""

import os
import time

import pytest
import requests

from claude_or.config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    get_model_mapping,
    get_provider_config,
    load_env,
)

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
            provider, max_tokens=100,
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
