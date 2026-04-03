"""Tests for claude_or.config — model mapping, env loading, YAML generation.

User Stories Covered:
  1. "I just want to run it" — default config generates valid YAML with wildcard patterns
  2. "I want to use a different model" — env var overrides change the backend per tier
  3. "I want a different port" — CLAUDE_OR_PORT env var is respected
  4. "I want to disable provider pinning" — empty OPENROUTER_PROVIDER omits provider block
  5. "I forgot my API key" — generate_config_yaml returns None when key is missing
  6. ".env from home dir" — load_env picks up ~/.claude-or/.env as fallback
"""

import os
import stat
import textwrap

import pytest
import yaml

from claude_or.config import (
    DEFAULT_MODEL,
    DEFAULT_PORT,
    DEFAULT_PROVIDER,
    ENV_TEMPLATE,
    MODEL_TIER_PATTERNS,
    bootstrap_env,
    generate_config_yaml,
    get_model_mapping,
    get_port,
    get_provider_config,
    load_env,
)


# ── Helpers ──────────────────────────────────────────────────────────────

ALL_TIER_PATTERNS = list(MODEL_TIER_PATTERNS.values())


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove all claude-or env vars before each test."""
    for var in [
        "OPENROUTER_API_KEY",
        "CLAUDE_SONNET_MODEL",
        "CLAUDE_OPUS_MODEL",
        "CLAUDE_HAIKU_MODEL",
        "OPENROUTER_PROVIDER",
        "CLAUDE_OR_PORT",
    ]:
        monkeypatch.delenv(var, raising=False)


# ── Story 1: Default config with all model names ────────────────────────


class TestDefaultModelMapping:
    """AC: All 3 tier wildcard patterns map to the default backend model."""

    def test_returns_all_three_tier_patterns(self):
        mapping = get_model_mapping()
        assert set(mapping.keys()) == set(ALL_TIER_PATTERNS)

    def test_all_default_to_kimi_k25(self):
        mapping = get_model_mapping()
        for pattern, backend in mapping.items():
            assert backend == DEFAULT_MODEL, f"{pattern} should default to {DEFAULT_MODEL}"

    def test_has_sonnet_pattern(self):
        mapping = get_model_mapping()
        assert "claude-sonnet*" in mapping

    def test_has_opus_pattern(self):
        mapping = get_model_mapping()
        assert "claude-opus*" in mapping

    def test_has_haiku_pattern(self):
        mapping = get_model_mapping()
        assert "claude-haiku*" in mapping


# ── Story 2: Override model per tier ─────────────────────────────────────


class TestModelOverrides:
    """AC: Setting CLAUDE_SONNET_MODEL (etc.) changes only that tier's backend."""

    def test_override_sonnet_only(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SONNET_MODEL", "openrouter/google/gemini-2.5-flash")
        mapping = get_model_mapping()

        assert mapping["claude-sonnet*"] == "openrouter/google/gemini-2.5-flash"
        # Other tiers unchanged
        assert mapping["claude-opus*"] == DEFAULT_MODEL
        assert mapping["claude-haiku*"] == DEFAULT_MODEL

    def test_override_opus_only(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_OPUS_MODEL", "openrouter/deepseek/deepseek-r1")
        mapping = get_model_mapping()

        assert mapping["claude-opus*"] == "openrouter/deepseek/deepseek-r1"
        assert mapping["claude-sonnet*"] == DEFAULT_MODEL

    def test_override_haiku_only(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_HAIKU_MODEL", "openrouter/meta/llama-4-scout")
        mapping = get_model_mapping()

        assert mapping["claude-haiku*"] == "openrouter/meta/llama-4-scout"

    def test_override_all_tiers(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SONNET_MODEL", "openrouter/model-a")
        monkeypatch.setenv("CLAUDE_OPUS_MODEL", "openrouter/model-b")
        monkeypatch.setenv("CLAUDE_HAIKU_MODEL", "openrouter/model-c")
        mapping = get_model_mapping()

        assert mapping["claude-sonnet*"] == "openrouter/model-a"
        assert mapping["claude-opus*"] == "openrouter/model-b"
        assert mapping["claude-haiku*"] == "openrouter/model-c"


# ── Story 3: Custom port ────────────────────────────────────────────────


class TestPort:
    """AC: Port defaults to 4000, can be overridden via CLAUDE_OR_PORT."""

    def test_default_port(self):
        assert get_port() == DEFAULT_PORT

    def test_custom_port_via_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_OR_PORT", "8080")
        assert get_port() == 8080

    def test_port_is_integer(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_OR_PORT", "3000")
        port = get_port()
        assert isinstance(port, int)


# ── Story 4: Provider pinning ────────────────────────────────────────────


class TestProviderConfig:
    """AC: Provider defaults to Together, can be changed or disabled."""

    def test_default_provider_is_fireworks(self):
        assert get_provider_config() == "Fireworks"

    def test_custom_provider(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_PROVIDER", "Fireworks")
        assert get_provider_config() == "Fireworks"

    def test_empty_provider_disables_pinning(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_PROVIDER", "")
        assert get_provider_config() is None


# ── Story 5: Missing API key ────────────────────────────────────────────


class TestMissingApiKey:
    """AC: generate_config_yaml returns None when OPENROUTER_API_KEY is not set."""

    def test_returns_none_without_api_key(self):
        assert generate_config_yaml() is None


# ── Story 1+2+4 combined: YAML generation ───────────────────────────────


class TestYamlGeneration:
    """AC: Generated YAML is valid, contains all model entries, and respects config."""

    @pytest.fixture()
    def config_path(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key-123")
        path = generate_config_yaml()
        yield path
        if path and os.path.exists(path):
            os.unlink(path)

    def test_generates_valid_yaml(self, config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_contains_all_three_tier_patterns(self, config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f)
        model_names = [entry["model_name"] for entry in data["model_list"]]
        assert set(model_names) == set(ALL_TIER_PATTERNS)

    def test_all_entries_use_api_key(self, config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f)
        for entry in data["model_list"]:
            assert entry["litellm_params"]["api_key"] == "sk-or-test-key-123"

    def test_all_entries_point_to_openrouter(self, config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f)
        for entry in data["model_list"]:
            assert entry["litellm_params"]["api_base"] == "https://openrouter.ai/api/v1"

    def test_drop_params_enabled(self, config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f)
        assert data["general_settings"]["drop_params"] is True
        assert data["litellm_settings"]["drop_params"] is True

    def test_default_provider_pinning_in_yaml(self, config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f)
        for entry in data["model_list"]:
            provider = entry["litellm_params"]["extra_body"]["provider"]
            assert "Fireworks" in provider["order"]
            assert provider["allow_fallbacks"] is True

    def test_no_provider_when_disabled(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.setenv("OPENROUTER_PROVIDER", "")
        path = generate_config_yaml()
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            for entry in data["model_list"]:
                assert "extra_body" not in entry["litellm_params"]
        finally:
            os.unlink(path)

    def test_custom_model_in_yaml(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.setenv("CLAUDE_SONNET_MODEL", "openrouter/custom/model")
        path = generate_config_yaml()
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            sonnet_entries = [
                e for e in data["model_list"] if "sonnet" in e["model_name"]
            ]
            for entry in sonnet_entries:
                assert entry["litellm_params"]["model"] == "openrouter/custom/model"
        finally:
            os.unlink(path)

    def test_temp_file_permissions_owner_only(self, config_path):
        file_stat = os.stat(config_path)
        mode = stat.S_IMODE(file_stat.st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_temp_file_is_cleaned_up(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        path = generate_config_yaml()
        assert os.path.exists(path)
        os.unlink(path)
        assert not os.path.exists(path)


# ── Story 6: .env file loading ───────────────────────────────────────────


class TestEnvFileLoading:
    """AC: .env is loaded from CWD first, then ~/.claude-or/.env as fallback."""

    def test_loads_from_cwd(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("OPENROUTER_API_KEY=sk-or-from-cwd\n")
        monkeypatch.chdir(tmp_path)
        load_env()
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-from-cwd"

    def test_loads_from_home_fallback(self, tmp_path, monkeypatch):
        # Simulate ~/.claude-or/.env
        claude_or_dir = tmp_path / ".claude-or"
        claude_or_dir.mkdir()
        env_file = claude_or_dir / ".env"
        env_file.write_text("OPENROUTER_API_KEY=sk-or-from-home\n")
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path)
        # No CWD .env
        monkeypatch.chdir(tmp_path / ".claude-or")  # dir without .env at CWD level
        load_env()
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-from-home"

    def test_cwd_takes_precedence_over_home(self, tmp_path, monkeypatch):
        # CWD .env
        cwd = tmp_path / "project"
        cwd.mkdir()
        (cwd / ".env").write_text("OPENROUTER_API_KEY=sk-or-cwd-wins\n")
        # Home .env
        claude_or_dir = tmp_path / ".claude-or"
        claude_or_dir.mkdir()
        (claude_or_dir / ".env").write_text("OPENROUTER_API_KEY=sk-or-home-loses\n")
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path)
        monkeypatch.chdir(cwd)
        load_env()
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-cwd-wins"

    def test_shell_env_takes_precedence_over_dotenv(self, tmp_path, monkeypatch):
        """Shell env vars should never be overwritten by .env files."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-from-shell")
        env_file = tmp_path / ".env"
        env_file.write_text("OPENROUTER_API_KEY=sk-or-from-file\n")
        monkeypatch.chdir(tmp_path)
        load_env()
        assert os.environ.get("OPENROUTER_API_KEY") == "sk-or-from-shell"


# ── Story 7: .env bootstrapping ─────────────────────────────────────────


class TestBootstrapEnv:
    """AC: Creates a starter .env when none exists, skips if one is found."""

    def test_creates_env_when_none_exists(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path / "fakehome")
        result = bootstrap_env()
        assert result is True
        assert (tmp_path / ".env").exists()

    def test_returns_true_when_created(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path / "fakehome")
        assert bootstrap_env() is True

    def test_env_has_uncommented_api_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path / "fakehome")
        bootstrap_env()
        content = (tmp_path / ".env").read_text()
        # Should have an uncommented OPENROUTER_API_KEY= line
        assert "\nOPENROUTER_API_KEY=" in content or content.startswith("OPENROUTER_API_KEY=")

    def test_env_has_commented_optional_vars(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path / "fakehome")
        bootstrap_env()
        content = (tmp_path / ".env").read_text()
        assert "# CLAUDE_SONNET_MODEL=" in content
        assert "# CLAUDE_OPUS_MODEL=" in content
        assert "# CLAUDE_HAIKU_MODEL=" in content
        assert "# OPENROUTER_PROVIDER=" in content
        assert "# CLAUDE_OR_PORT=" in content

    def test_content_matches_template(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("claude_or.config.Path.home", lambda: tmp_path / "fakehome")
        bootstrap_env()
        content = (tmp_path / ".env").read_text()
        assert content == ENV_TEMPLATE

    def test_no_create_when_cwd_env_exists(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("OPENROUTER_API_KEY=existing\n")
        monkeypatch.chdir(tmp_path)
        result = bootstrap_env()
        assert result is False
        # Original content unchanged
        assert (tmp_path / ".env").read_text() == "OPENROUTER_API_KEY=existing\n"

    def test_no_create_when_home_env_exists(self, tmp_path, monkeypatch):
        fakehome = tmp_path / "fakehome"
        claude_or_dir = fakehome / ".claude-or"
        claude_or_dir.mkdir(parents=True)
        (claude_or_dir / ".env").write_text("OPENROUTER_API_KEY=from-home\n")
        monkeypatch.setattr("claude_or.config.Path.home", lambda: fakehome)
        cwd = tmp_path / "project"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        result = bootstrap_env()
        assert result is False
        assert not (cwd / ".env").exists()
