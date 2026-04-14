"""Multi-provider LLM caller for phase PO stages.

Tries providers in order until one returns text:

1. Explicit override via ``CALORON_LLM_PROVIDER`` env var.
2. Subscription CLIs on PATH (``claude``, ``gemini``, ``cursor-agent``,
   ``opencode``). Uses the user's authenticated session — no API key
   needed. Only works when the stage runs outside a sandboxed nix
   executor (i.e. via direct Python invocation or caloron's CLI shell).
3. HTTPS APIs when the matching key is set (``ANTHROPIC_API_KEY``,
   ``OPENAI_API_KEY``, ``GOOGLE_API_KEY``). Works everywhere urllib works,
   including Noether's nix executor.
4. Returns ``None`` if nothing is available — caller should fall back
   to deterministic template logic.

This module is co-located with the phase stages and is concatenated
into each stage's implementation at register_phases.sh time so stages
remain hermetic when registered with Noether. In the repo it's a
regular module that tests import directly.
"""

import json as _json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

# Ordered list of providers consulted automatically when no override.
_PROVIDER_ORDER = (
    "claude-cli",
    "gemini-cli",
    "cursor-cli",
    "opencode",
    "anthropic-api",
    "openai-api",
    "gemini-api",
)

_DEFAULT_MODELS = {
    "anthropic-api": "claude-sonnet-4-5",
    "openai-api": "gpt-4o",
    "gemini-api": "gemini-1.5-pro",
}


def _subproc(argv: list[str], prompt: str, timeout: int) -> str | None:
    """Run a CLI agent in print/headless mode; return stdout or None on failure.

    Timeout is capped at 25s to stay under Noether's default 30s stage
    kill — inside the nix sandbox a subscription CLI often stalls (auth
    state isn't mounted) and we'd rather fall through to an HTTPS
    provider than get killed by the runner.
    """
    try:
        r = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=min(timeout, 25),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    return out or None


def _claude_cli(prompt: str, timeout: int) -> str | None:
    if not shutil.which("claude"):
        return None
    # `claude -p "<prompt>"` runs non-interactively using the local session
    # (subscription OR ANTHROPIC_API_KEY, whichever claude-code is configured for).
    return _subproc(["claude", "--dangerously-skip-permissions", "-p", prompt], "", timeout)


def _gemini_cli(prompt: str, timeout: int) -> str | None:
    if not shutil.which("gemini"):
        return None
    return _subproc(["gemini", "-y", "-p", prompt], "", timeout)


def _cursor_cli(prompt: str, timeout: int) -> str | None:
    if not shutil.which("cursor-agent"):
        return None
    return _subproc(["cursor-agent", "-p", prompt, "--output-format", "text"], "", timeout)


def _opencode_cli(prompt: str, timeout: int) -> str | None:
    if not shutil.which("opencode"):
        return None
    return _subproc(["opencode", "run", prompt], "", timeout)


def _post_json(url: str, body: dict, headers: dict, timeout: int) -> dict | None:
    req = urllib.request.Request(
        url, data=_json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return _json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _anthropic_api(prompt: str, timeout: int) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("CALORON_LLM_MODEL", _DEFAULT_MODELS["anthropic-api"])
    resp = _post_json(
        _ANTHROPIC_ENDPOINT,
        {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        timeout,
    )
    if not resp:
        return None
    content = resp.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text")
        if isinstance(text, str):
            return text
    return None


def _openai_api(prompt: str, timeout: int) -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    model = os.environ.get("CALORON_LLM_MODEL", _DEFAULT_MODELS["openai-api"])
    resp = _post_json(
        _OPENAI_ENDPOINT,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
        timeout,
    )
    if not resp:
        return None
    choices = resp.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        text = message.get("content")
        if isinstance(text, str):
            return text
    return None


def _gemini_api(prompt: str, timeout: int) -> str | None:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        return None
    model = os.environ.get("CALORON_LLM_MODEL", _DEFAULT_MODELS["gemini-api"])
    url = _GEMINI_ENDPOINT.format(model=model, key=key)
    resp = _post_json(
        url,
        {"contents": [{"parts": [{"text": prompt}]}]},
        {"content-type": "application/json"},
        timeout,
    )
    if not resp:
        return None
    candidates = resp.get("candidates")
    if isinstance(candidates, list) and candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts and isinstance(parts, list):
            text = parts[0].get("text")
            if isinstance(text, str):
                return text
    return None


# Maps provider id → name of the dispatch function in this module. The
# indirection lets monkeypatch-based tests replace _claude_cli et al and
# have the change take effect — a dict of direct function refs would
# snapshot the originals at import time.
_DISPATCH = {
    "claude-cli": "_claude_cli",
    "gemini-cli": "_gemini_cli",
    "cursor-cli": "_cursor_cli",
    "opencode": "_opencode_cli",
    "anthropic-api": "_anthropic_api",
    "openai-api": "_openai_api",
    "gemini-api": "_gemini_api",
}


_CLI_PROVIDERS = {"claude-cli", "gemini-cli", "cursor-cli", "opencode"}


def call_llm(prompt: str, timeout: int = 120) -> str | None:
    """Try every configured provider in order; return the first non-empty result.

    Set ``CALORON_LLM_SKIP_CLI=1`` to skip subprocess-based providers in
    the auto-chain. Intended for sandboxed environments (like Noether's
    nix executor) where CLI auth state isn't mounted and subprocess
    calls stall. Explicit ``CALORON_LLM_PROVIDER`` always wins.
    """
    override = os.environ.get("CALORON_LLM_PROVIDER", "").strip()
    skip_cli = os.environ.get("CALORON_LLM_SKIP_CLI", "").strip() in ("1", "true", "yes")

    if override:
        providers = [override]
    elif skip_cli:
        providers = [p for p in _PROVIDER_ORDER if p not in _CLI_PROVIDERS]
    else:
        providers = list(_PROVIDER_ORDER)

    for name in providers:
        fn_name = _DISPATCH.get(name)
        if fn_name is None:
            continue
        fn = globals().get(fn_name)
        if fn is None:
            continue
        text = fn(prompt, timeout)
        if text:
            return text
    return None
