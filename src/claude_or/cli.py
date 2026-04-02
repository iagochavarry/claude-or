"""claude-or: Route Claude Code through OpenRouter."""

import argparse
import atexit
import os
import signal
import sys
import threading

from claude_or import __version__
from claude_or.config import (
    DEFAULT_PORT,
    generate_config_yaml,
    get_model_mapping,
    get_port,
    get_provider_config,
    load_env,
)
from claude_or.logger import inject_callback, suppress_noisy_loggers

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"


def _print_banner(port, mapping, provider):
    """Print startup banner with routing table."""
    # Group by tier for display
    tiers = {}
    for claude_name, backend in mapping.items():
        # Extract tier from model name
        for tier in ("sonnet", "opus", "haiku"):
            if tier in claude_name:
                # Strip openrouter/ prefix for display
                display_model = backend.removeprefix("openrouter/")
                provider_tag = f" ({provider})" if provider else ""
                tiers[tier] = f"{display_model}{provider_tag}"
                break

    print(f"\n{GREEN}{BOLD}claude-or{RESET} v{__version__} — proxy running on {CYAN}http://localhost:{port}{RESET}\n")
    print(f"  {BOLD}Routing:{RESET}")
    for tier in ("sonnet", "opus", "haiku"):
        if tier in tiers:
            print(f"    {tier:8s} → {tiers[tier]}")
    print()
    print(f"  {BOLD}Connect Claude Code:{RESET}")
    print(f"    {DIM}ANTHROPIC_BASE_URL=http://localhost:{port} ANTHROPIC_AUTH_TOKEN=sk-placeholder claude{RESET}")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="claude-or",
        description="Route Claude Code through OpenRouter to alternative models",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=None,
        help=f"proxy port (default: {DEFAULT_PORT}, or CLAUDE_OR_PORT env var)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="show litellm debug logs",
    )
    args = parser.parse_args()

    # Load environment
    load_env()

    # Override port from CLI flag
    if args.port is not None:
        os.environ["CLAUDE_OR_PORT"] = str(args.port)

    # Validate API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(f"\n{RED}{BOLD}Error: OPENROUTER_API_KEY not set.{RESET}\n")
        print("Set it in one of:")
        print("  1. Environment variable: export OPENROUTER_API_KEY=sk-or-...")
        print("  2. .env file in current directory")
        print("  3. ~/.claude-or/.env")
        print()
        sys.exit(1)

    # Generate config
    config_path = generate_config_yaml()
    if not config_path:
        print(f"{RED}Failed to generate config.{RESET}")
        sys.exit(1)

    def _cleanup():
        try:
            os.unlink(config_path)
        except OSError:
            pass

    atexit.register(_cleanup)

    def _signal_handler(sig, frame):
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    port = get_port()
    mapping = get_model_mapping()
    provider = get_provider_config()

    # Suppress noisy logs unless verbose
    if not args.verbose:
        suppress_noisy_loggers()

    # Inject custom logger after proxy starts
    threading.Thread(target=_post_init, args=(args.verbose,), daemon=True).start()

    # Print banner
    _print_banner(port, mapping, provider)

    # Start LiteLLM proxy
    from litellm.proxy.proxy_cli import run_server
    sys.argv = ["litellm", "--config", config_path, "--port", str(port)]
    run_server()


def _post_init(verbose):
    """Post-initialization: inject logger, suppress late-created loggers."""
    inject_callback()
    if not verbose:
        import logging
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


if __name__ == "__main__":
    main()
