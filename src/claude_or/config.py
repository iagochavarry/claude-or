"""Configuration loading and YAML generation for claude-or proxy."""

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "openrouter/moonshotai/kimi-k2.5"

ENV_TEMPLATE = """\
# Required — get your key at https://openrouter.ai/keys
OPENROUTER_API_KEY=

# Optional: override which model each Claude tier routes to
# CLAUDE_SONNET_MODEL=openrouter/moonshotai/kimi-k2.5
# CLAUDE_OPUS_MODEL=openrouter/moonshotai/kimi-k2.5
# CLAUDE_HAIKU_MODEL=openrouter/moonshotai/kimi-k2.5

# Optional: provider pinning (default: Together, set empty to disable)
# OPENROUTER_PROVIDER=Fireworks

# Optional: proxy port (default: 4000)
# CLAUDE_OR_PORT=4000
"""
DEFAULT_PROVIDER = "Fireworks"
DEFAULT_PORT = 4000

# Claude model names grouped by tier
MODEL_TIERS = {
    "sonnet": ["claude-sonnet-4-20250514", "claude-sonnet-4-6"],
    "opus": ["claude-opus-4-20250514", "claude-opus-4-6"],
    "haiku": ["claude-haiku-4-5-20251001", "claude-haiku-4-5"],
}

# Env var name for each tier
TIER_ENV_VARS = {
    "sonnet": "CLAUDE_SONNET_MODEL",
    "opus": "CLAUDE_OPUS_MODEL",
    "haiku": "CLAUDE_HAIKU_MODEL",
}


def bootstrap_env():
    """Create a starter .env file if none exists anywhere.

    Returns True if a file was created, False otherwise.
    """
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return False

    global_env = Path.home() / ".claude-or" / ".env"
    if global_env.exists():
        return False

    cwd_env.write_text(ENV_TEMPLATE)
    return True


def load_env():
    """Load .env from CWD first, then ~/.claude-or/.env as fallback."""
    # CWD .env (higher priority)
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env, override=False)

    # Global fallback
    global_env = Path.home() / ".claude-or" / ".env"
    if global_env.exists():
        load_dotenv(global_env, override=False)


def get_model_mapping():
    """Return dict of {claude_model_name: backend_model} from env vars."""
    mapping = {}
    for tier, names in MODEL_TIERS.items():
        env_var = TIER_ENV_VARS[tier]
        backend = os.environ.get(env_var, DEFAULT_MODEL)
        for name in names:
            mapping[name] = backend
    return mapping


def get_provider_config():
    """Return provider pinning string, or None if disabled."""
    provider = os.environ.get("OPENROUTER_PROVIDER", DEFAULT_PROVIDER)
    if not provider:
        return None
    return provider


def get_port():
    """Return configured port."""
    return int(os.environ.get("CLAUDE_OR_PORT", DEFAULT_PORT))


def _build_model_entry(claude_name, backend_model, api_key, provider):
    """Build a single model_list entry as a YAML string."""
    lines = [
        f"  - model_name: {claude_name}",
        f"    litellm_params:",
        f"      model: {backend_model}",
        f"      api_base: https://openrouter.ai/api/v1",
        f"      api_key: {api_key}",
    ]
    if provider:
        lines.extend([
            f"      extra_body:",
            f"        provider:",
            f"          order:",
            f"            - {provider}",
            f"          allow_fallbacks: true",
        ])
    return "\n".join(lines)


def generate_config_yaml():
    """Generate LiteLLM config YAML from env vars and write to a temp file.

    Returns the path to the temp file.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    mapping = get_model_mapping()
    provider = get_provider_config()

    entries = []
    for claude_name, backend_model in mapping.items():
        entries.append(_build_model_entry(claude_name, backend_model, api_key, provider))

    yaml_content = f"""model_list:
{chr(10).join(entries)}

general_settings:
  drop_params: true

litellm_settings:
  drop_params: true
"""

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="claude_or_", delete=False
    )
    tmp.write(yaml_content)
    tmp.close()
    os.chmod(tmp.name, 0o600)
    return tmp.name
