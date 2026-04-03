"""claude-or: Route Claude Code through OpenRouter."""

import argparse
import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

from claude_or import __version__
from claude_or.config import (
    DEFAULT_PORT,
    bootstrap_env,
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


def _print_banner(port, mapping, provider, auto_launch=True):
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
    if auto_launch:
        print(f"  {BOLD}Launching Claude Code...{RESET}")
        print()
    else:
        print(f"  {BOLD}Connect Claude Code:{RESET}")
        print(f"    {DIM}ANTHROPIC_BASE_URL=http://localhost:{port} ANTHROPIC_AUTH_TOKEN=sk-placeholder claude{RESET}")
        print()


def _wait_for_port(port, timeout=30):
    """Block until localhost:port is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _launch_claude(port):
    """Launch Claude Code pointing at our proxy. Returns the Popen object or None."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        print(f"{RED}{BOLD}Error: 'claude' not found in PATH.{RESET}")
        print("Install Claude Code: https://docs.anthropic.com/en/docs/claude-code")
        return None

    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = f"http://localhost:{port}"
    env["ANTHROPIC_AUTH_TOKEN"] = "sk-placeholder"

    return subprocess.Popen([claude_bin], env=env)


def _run_proxy(config_path, port):
    """Run the LiteLLM proxy server (blocking, meant for a daemon thread)."""
    from litellm.proxy.proxy_cli import run_server
    sys.argv = ["litellm", "--config", config_path, "--port", str(port)]
    run_server()


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
    parser.add_argument(
        "--proxy-only", action="store_true",
        help="only start the proxy, don't launch Claude Code",
    )
    args = parser.parse_args()

    # Bootstrap .env if none exists
    if bootstrap_env():
        print(f"\n{GREEN}{BOLD}Created .env file in current directory.{RESET}")
        print(f"Edit it to add your OpenRouter API key, then run {CYAN}claude-or{RESET} again.\n")
        sys.exit(0)

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

    port = get_port()
    mapping = get_model_mapping()
    provider = get_provider_config()
    auto_launch = not args.proxy_only

    # Suppress noisy logs unless verbose
    if not args.verbose:
        suppress_noisy_loggers()

    # Print banner
    _print_banner(port, mapping, provider, auto_launch=auto_launch)

    if not auto_launch:
        # Original behavior: run proxy in main thread
        def _signal_handler(sig, frame):
            _cleanup()
            sys.exit(0)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        threading.Thread(target=_post_init, args=(args.verbose,), daemon=True).start()

        from litellm.proxy.proxy_cli import run_server
        sys.argv = ["litellm", "--config", config_path, "--port", str(port)]
        run_server()
        return

    # Auto-launch mode: proxy in daemon thread, claude as subprocess
    claude_proc = None

    def _signal_handler(sig, frame):
        if claude_proc and claude_proc.poll() is None:
            claude_proc.terminate()
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Start proxy in daemon thread
    proxy_thread = threading.Thread(
        target=_run_proxy, args=(config_path, port),
        daemon=True,
    )
    proxy_thread.start()

    # Inject custom logger after proxy starts
    threading.Thread(target=_post_init, args=(args.verbose,), daemon=True).start()

    # Wait for proxy to be ready
    if not _wait_for_port(port):
        print(f"{RED}{BOLD}Error: Proxy failed to start within 30 seconds.{RESET}")
        sys.exit(1)

    # Launch Claude Code
    claude_proc = _launch_claude(port)
    if claude_proc is None:
        sys.exit(1)

    # Wait for Claude to exit
    try:
        returncode = claude_proc.wait()
    except KeyboardInterrupt:
        claude_proc.terminate()
        try:
            claude_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            claude_proc.kill()
        returncode = 130

    _cleanup()
    sys.exit(returncode)


def _post_init(verbose):
    """Post-initialization: inject logger, suppress late-created loggers."""
    inject_callback()
    if not verbose:
        import logging
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


if __name__ == "__main__":
    main()
