"""Tests for claude_or.cli — argument parsing, error handling, banner output.

User Stories Covered:
  1. "I just want to run it" — CLI parses args and prints banner
  3. "I want a different port" — --port flag works
  4. "I forgot my API key" — exits with code 1 and helpful message
  7. ".env bootstrapping" — creates .env when missing, exits with instructions
  8. "Auto-launch" — proxy starts, claude launched automatically
"""

import os
import socket
import subprocess
import sys
import threading

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
        """A temp directory with an empty .env file (no API key set).

        We create a .env so bootstrap_env() is skipped, but without a key
        so the missing-key error path is triggered.
        """
        (tmp_path / ".env").write_text("# empty\n")
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

    def test_banner_shows_connection_command_in_proxy_only_mode(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or.cli import _print_banner

        mapping = {"claude-sonnet-4-6": "openrouter/moonshotai/kimi-k2.5"}
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(8080, mapping, None, auto_launch=False)
        output = buf.getvalue()
        assert "ANTHROPIC_BASE_URL=http://localhost:8080" in output
        assert "ANTHROPIC_AUTH_TOKEN=sk-placeholder" in output

    def test_banner_shows_launching_message_in_auto_mode(self):
        from io import StringIO
        from unittest.mock import patch

        from claude_or.cli import _print_banner

        mapping = {"claude-sonnet-4-6": "openrouter/moonshotai/kimi-k2.5"}
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_banner(4000, mapping, None, auto_launch=True)
        output = buf.getvalue()
        assert "Launching Claude Code" in output
        assert "ANTHROPIC_BASE_URL" not in output

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


# ── Story: --proxy-only flag ────────────────────────────────────────────


class TestProxyOnlyFlag:
    """AC: --proxy-only flag is shown in help."""

    def test_help_shows_proxy_only_flag(self):
        result = run_claude_or("--help")
        assert "--proxy-only" in result.stdout


class TestClaudeOnlyFlag:
    """AC: --claude-only flag connects to existing proxy without starting one."""

    def test_help_shows_claude_only_flag(self):
        result = run_claude_or("--help")
        assert "--claude-only" in result.stdout

    def test_mutually_exclusive_with_proxy_only(self):
        result = run_claude_or("--claude-only", "--proxy-only")
        assert result.returncode != 0


# ── Story: .env bootstrapping via CLI ───────────────────────────────────


class TestEnvBootstrap:
    """AC: When no .env exists, creates one and exits with instructions."""

    def test_creates_env_and_exits_zero(self, tmp_path):
        result = run_claude_or(cwd=tmp_path)
        assert result.returncode == 0
        assert (tmp_path / ".env").exists()

    def test_prints_instructions(self, tmp_path):
        result = run_claude_or(cwd=tmp_path)
        assert "Created .env" in result.stdout
        assert "claude-or" in result.stdout

    def test_created_env_has_api_key_placeholder(self, tmp_path):
        run_claude_or(cwd=tmp_path)
        content = (tmp_path / ".env").read_text()
        assert "OPENROUTER_API_KEY=" in content


# ── Story: Port wait helper ─────────────────────────────────────────────


class TestWaitForPort:
    """AC: _wait_for_port returns True when port is open, False on timeout."""

    def test_returns_true_when_port_open(self):
        from claude_or.cli import _wait_for_port

        # Start a simple TCP server
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("localhost", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            assert _wait_for_port(port, timeout=3) is True
        finally:
            srv.close()

    def test_returns_false_on_timeout(self):
        from claude_or.cli import _wait_for_port

        # Use a port that's almost certainly not listening
        assert _wait_for_port(19999, timeout=1) is False


# ── Story: Claude launcher ──────────────────────────────────────────────


class TestLaunchClaude:
    """AC: _launch_claude finds claude in PATH and sets correct env vars."""

    def test_returns_none_when_claude_not_in_path(self, monkeypatch):
        from claude_or.cli import _launch_claude

        monkeypatch.setattr("shutil.which", lambda cmd: None)
        assert _launch_claude(4000) is None

    def test_launches_with_correct_env_vars(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        from claude_or.cli import _launch_claude

        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/claude")
        mock_popen = MagicMock()
        with patch("claude_or.cli.subprocess.Popen", return_value=mock_popen) as popen_call:
            result = _launch_claude(8080)
            assert result is mock_popen
            call_kwargs = popen_call.call_args
            env = call_kwargs[1]["env"]
            assert env["ANTHROPIC_BASE_URL"] == "http://localhost:8080"
            assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-placeholder"

    def test_forwards_extra_args(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        from claude_or.cli import _launch_claude

        monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/claude")
        mock_popen = MagicMock()
        with patch("claude_or.cli.subprocess.Popen", return_value=mock_popen) as popen_call:
            _launch_claude(4000, ["--headless", "-p", "fix the bug"])
            cmd = popen_call.call_args[0][0]
            assert cmd == ["/usr/bin/claude", "--headless", "-p", "fix the bug"]
