"""Tests for claude_or.cli — argument parsing, error handling, banner output.

User Stories Covered:
  1. "I just want to run it" — CLI parses args and prints banner
  3. "I want a different port" — --port flag works
  4. "I forgot my API key" — exits with code 1 and helpful message
"""

import os
import subprocess
import sys

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────

def run_claude_or(*args, env_override=None, cwd=None):
    """Run claude-or as a subprocess and capture output."""
    env = os.environ.copy()
    # Strip any existing config that might interfere
    for var in [
        "OPENROUTER_API_KEY", "CLAUDE_SONNET_MODEL", "CLAUDE_OPUS_MODEL",
        "CLAUDE_HAIKU_MODEL", "OPENROUTER_PROVIDER", "CLAUDE_OR_PORT",
    ]:
        env.pop(var, None)
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        [sys.executable, "-m", "claude_or.cli", *args],
        capture_output=True, text=True, timeout=10, env=env,
        cwd=cwd,
    )
    return result


# ── Story: Missing API key gives clear error ─────────────────────────────


class TestMissingApiKeyError:
    """AC: Running without OPENROUTER_API_KEY exits with code 1 and shows help."""

    @pytest.fixture()
    def no_env_dir(self, tmp_path):
        """A temp directory with no .env file, so the key won't be loaded."""
        return tmp_path

    def test_exit_code_is_1(self, no_env_dir):
        result = run_claude_or(cwd=no_env_dir)
        assert result.returncode == 1

    def test_error_message_mentions_env_var(self, no_env_dir):
        result = run_claude_or(cwd=no_env_dir)
        assert "OPENROUTER_API_KEY" in result.stdout

    def test_error_message_shows_three_options(self, no_env_dir):
        result = run_claude_or(cwd=no_env_dir)
        assert "Environment variable" in result.stdout
        assert ".env file in current directory" in result.stdout
        assert "~/.claude-or/.env" in result.stdout


# ── Story: --help flag works ─────────────────────────────────────────────


class TestHelpFlag:
    """AC: --help shows usage without requiring API key."""

    def test_help_exits_zero(self):
        result = run_claude_or("--help")
        assert result.returncode == 0

    def test_help_shows_description(self):
        result = run_claude_or("--help")
        assert "Route Claude Code through OpenRouter" in result.stdout

    def test_help_shows_port_flag(self):
        result = run_claude_or("--help")
        assert "--port" in result.stdout
        assert "-p" in result.stdout

    def test_help_shows_verbose_flag(self):
        result = run_claude_or("--help")
        assert "--verbose" in result.stdout
        assert "-v" in result.stdout


# ── Story: Banner displays correct info ──────────────────────────────────


class TestBanner:
    """AC: Startup banner shows version, routing table, and connection instructions.

    Note: We can't fully start the proxy in tests (it binds a port), so we test
    the banner function directly.
    """

    def test_banner_contains_version(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or import __version__
        from claude_or.cli import _print_banner
        from claude_or.config import DEFAULT_MODEL

        mapping = {"claude-sonnet-4-6": DEFAULT_MODEL}
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(4000, mapping, "Together")
        output = buf.getvalue()
        assert __version__ in output

    def test_banner_shows_routing(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or.cli import _print_banner

        mapping = {
            "claude-sonnet-4-6": "openrouter/moonshotai/kimi-k2.5",
            "claude-opus-4-6": "openrouter/deepseek/deepseek-r1",
        }
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(4000, mapping, "Together")
        output = buf.getvalue()
        assert "moonshotai/kimi-k2.5" in output
        assert "deepseek/deepseek-r1" in output

    def test_banner_shows_connection_command(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or.cli import _print_banner

        mapping = {"claude-sonnet-4-6": "openrouter/moonshotai/kimi-k2.5"}
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(8080, mapping, None)
        output = buf.getvalue()
        assert "ANTHROPIC_BASE_URL=http://localhost:8080" in output
        assert "ANTHROPIC_AUTH_TOKEN=sk-placeholder" in output

    def test_banner_omits_provider_when_none(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or.cli import _print_banner

        mapping = {"claude-sonnet-4-6": "openrouter/moonshotai/kimi-k2.5"}
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(4000, mapping, None)
        output = buf.getvalue()
        assert "(Together)" not in output

    def test_banner_strips_openrouter_prefix(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or.cli import _print_banner

        mapping = {"claude-sonnet-4-6": "openrouter/moonshotai/kimi-k2.5"}
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(4000, mapping, "Together")
        output = buf.getvalue()
        # Should show "moonshotai/kimi-k2.5", not "openrouter/moonshotai/kimi-k2.5"
        assert "openrouter/moonshotai" not in output
        assert "moonshotai/kimi-k2.5" in output
