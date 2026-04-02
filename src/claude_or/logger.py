"""Concise colorized logger for LiteLLM proxy requests/responses."""

import time
import logging
import litellm
from datetime import datetime
from litellm.integrations.custom_logger import CustomLogger

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[96m"

SEP = f"{DIM}{'─' * 50}{RESET}"

NOISY_LOGGERS = [
    "LiteLLM",
    "LiteLLM Proxy",
    "LiteLLM Router",
    "httpx",
    "uvicorn.access",
]


def extract_text(content, max_len=120):
    """Extract readable text from message content (string or Anthropic content blocks)."""
    if not content:
        return ""
    if isinstance(content, str):
        return content[:max_len].replace("\n", " ")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", "")[:max_len])
                elif block.get("type") == "tool_result":
                    parts.append("[tool_result]")
                elif block.get("type") == "thinking":
                    parts.append("[thinking]")
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool: {block.get('name', '?')}]")
                else:
                    parts.append(f"[{block.get('type', '?')}]")
        return " ".join(parts)[:max_len]
    return str(content)[:max_len]


class ConciseLogger(CustomLogger):

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        ts = datetime.now().strftime("%H:%M:%S")
        model = data.get("model", "?")
        messages = data.get("messages", [])
        n = len(messages)

        print(f"\n{SEP}", flush=True)
        print(f"{BLUE}{BOLD}\u2192 {ts}  {model}{RESET}  {DIM}({n} msgs){RESET}", flush=True)

        for msg in reversed(messages):
            if msg.get("role") == "user":
                text = extract_text(msg.get("content", ""))
                print(f"  {CYAN}> {text}{RESET}", flush=True)
                break

        return None

    def _log_output(self, kwargs, response_obj, start_time, end_time):
        ts = datetime.now().strftime("%H:%M:%S")
        elapsed = (end_time - start_time).total_seconds()

        usage = getattr(response_obj, "usage", None)
        prompt_t = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_t = getattr(usage, "completion_tokens", 0) if usage else 0

        content = ""
        try:
            d = response_obj.model_dump() if hasattr(response_obj, "model_dump") else {}
            choices = d.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning_content") or ""
        except Exception:
            pass

        preview = content[:150].replace("\n", " ")

        print(
            f"{GREEN}{BOLD}\u2190 {ts}  {YELLOW}{elapsed:.1f}s{RESET}  "
            f"{DIM}{prompt_t}\u2192{completion_t} tok{RESET}",
            flush=True,
        )
        if preview:
            print(f"  {DIM}< {preview}{RESET}", flush=True)

    def _log_error(self, kwargs, start_time, end_time):
        ts = datetime.now().strftime("%H:%M:%S")
        elapsed = (end_time - start_time).total_seconds()
        error = kwargs.get("exception", "unknown")
        print(f"{RED}{BOLD}\u2717 {ts}  {elapsed:.1f}s  ERROR: {str(error)[:150]}{RESET}", flush=True)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._log_output(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._log_error(kwargs, start_time, end_time)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._log_output(kwargs, response_obj, start_time, end_time)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._log_error(kwargs, start_time, end_time)


_logger_instance = ConciseLogger()


def inject_callback():
    """Wait for proxy to initialize, then inject our callback."""
    for _ in range(30):
        time.sleep(1)
        if isinstance(litellm.callbacks, list):
            if _logger_instance not in litellm.callbacks:
                litellm.callbacks.append(_logger_instance)
                print(f"{GREEN}{BOLD}\u2713 Logger ready{RESET}\n", flush=True)
            return
    litellm.callbacks = [_logger_instance]
    print(f"{GREEN}{BOLD}\u2713 Logger ready (fallback){RESET}\n", flush=True)


def suppress_noisy_loggers():
    """Suppress verbose logs from LiteLLM, uvicorn, httpx."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
