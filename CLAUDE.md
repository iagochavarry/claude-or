# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`claude-or` — a pip-installable CLI tool that routes Claude Code requests through OpenRouter to alternative models (default: Kimi K2.5 via Together). Powered by LiteLLM proxy.

## Development

```bash
# Install in editable mode
pip install -e .

# Run
claude-or

# Run with verbose logging
claude-or -v
```

Requires a `.env` file with `OPENROUTER_API_KEY=sk-or-...` (see `.env.example`).

To use with Claude Code:
```bash
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_AUTH_TOKEN=sk-placeholder claude
```

## Project Structure

- `src/claude_or/cli.py` — CLI entry point, startup banner, argparse
- `src/claude_or/config.py` — .env loading, model mapping, YAML generation
- `src/claude_or/logger.py` — ConciseLogger for colorized request/response logs
- `pyproject.toml` — package config, `claude-or` script entry point
- `tests/` — pytest test suite (56 tests)

## Configuration

All via environment variables or `.env` file. See `.env.example` for the full list.

Key env vars: `OPENROUTER_API_KEY` (required), `CLAUDE_SONNET_MODEL`, `CLAUDE_OPUS_MODEL`, `CLAUDE_HAIKU_MODEL`, `OPENROUTER_PROVIDER`, `CLAUDE_OR_PORT`.
