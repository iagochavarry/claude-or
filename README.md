# claude-or

Route Claude Code through OpenRouter to alternative models. One command, zero config files.

## Quick Start

### 1. Install

```bash
# From GitHub
pipx install 'claude-or @ git+https://github.com/iagochavarry/claude-or.git'

# Or with pip
pip install 'claude-or @ git+https://github.com/iagochavarry/claude-or.git'
```

### 2. Configure

Create a `.env` file (in your working directory or `~/.claude-or/.env`):

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### 3. Run

```bash
claude-or
```

Then in another terminal:

```bash
ANTHROPIC_BASE_URL=http://localhost:4000 ANTHROPIC_AUTH_TOKEN=sk-placeholder claude
```

That's it. All Claude model requests are now routed through OpenRouter.

## Configuration

All configuration is via environment variables or `.env` file:

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | *required* | Your OpenRouter API key |
| `CLAUDE_SONNET_MODEL` | `openrouter/moonshotai/kimi-k2.5` | Backend for Sonnet requests |
| `CLAUDE_OPUS_MODEL` | `openrouter/moonshotai/kimi-k2.5` | Backend for Opus requests |
| `CLAUDE_HAIKU_MODEL` | `openrouter/moonshotai/kimi-k2.5` | Backend for Haiku requests |
| `OPENROUTER_PROVIDER` | `Together` | Provider pinning (empty = no pinning) |
| `CLAUDE_OR_PORT` | `4000` | Proxy port |

### CLI Flags

```bash
claude-or -p 4001      # custom port
claude-or -v           # verbose logging
```

## How It Works

Claude Code sends requests to `http://localhost:4000` thinking it's talking to Anthropic's API. The proxy (powered by [LiteLLM](https://github.com/BerriAI/litellm)) translates the request format and routes it to your configured model on OpenRouter.

```
Claude Code → localhost:4000 → LiteLLM Proxy → OpenRouter → Your Model
```

### Why LiteLLM?

- Translates between Anthropic message format and OpenAI chat format
- `drop_params` silently discards Anthropic-specific fields that would cause errors
- Provider pinning ensures consistent backend quality
- Production-grade, actively maintained

## .env File Lookup Order

1. `.env` in current working directory
2. `~/.claude-or/.env`
3. Shell environment variables

Shell env vars always take precedence over `.env` files.
