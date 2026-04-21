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
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

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
    # --dangerously-skip-permissions disables Claude Code's tool-permission
    # prompts; we only pass it when the operator explicitly opts in via
    # CALORON_ALLOW_DANGEROUS_CLAUDE (same gate used by orchestrator.*).
    dangerous = os.environ.get("CALORON_ALLOW_DANGEROUS_CLAUDE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    argv = ["claude"]
    if dangerous:
        argv.append("--dangerously-skip-permissions")
    argv.extend(["-p", prompt])
    return _subproc(argv, "", timeout)


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


# Ids caloron uses are 1:1 with the llm-here registry as of llm-here
# v0.1: claude-cli, gemini-cli, cursor-cli, opencode, anthropic-api,
# openai-api, gemini-api. Mistral is in llm-here v0.3 but caloron
# doesn't declare it; we simply don't forward Mistral overrides.
_LLM_HERE_KNOWN_IDS = {
    "claude-cli",
    "gemini-cli",
    "cursor-cli",
    "opencode",
    "anthropic-api",
    "openai-api",
    "gemini-api",
}


def _call_via_llm_here(prompt: str, timeout: int) -> str | None:
    """Try to dispatch via the shared ``llm-here`` binary.

    Returns the provider's text on success, or ``None`` on any failure
    (binary missing, non-zero exit, bad JSON, empty text). A ``None``
    return signals the caller to fall back to the in-tree local
    providers — this keeps llm-here a **soft dependency** through the
    migration window. Once llm-here is ubiquitous in caloron
    deployments, the fallback path (and the bulk of this module) can
    be deleted in a follow-up PR.

    Forwarded knobs:

    - ``CALORON_LLM_PROVIDER`` → ``--provider <id>``.
    - ``CALORON_LLM_SKIP_CLI`` — honoured natively by llm-here as one
      of four aliases, so it doesn't need explicit forwarding.
    - ``CALORON_ALLOW_DANGEROUS_CLAUDE`` → ``--dangerous-claude``.
    - ``timeout`` — caller-supplied, clamped to 300 s before forwarding
      so a runaway ``timeout`` kwarg doesn't stretch the subprocess past
      five minutes. llm-here applies its own per-provider timeouts
      below this ceiling.

    Every failure path logs a ``logger.debug`` breadcrumb so deployments
    stuck on the fallback can see *why* via ``logging.basicConfig(
    level=logging.DEBUG)``.
    """
    if not shutil.which("llm-here"):
        logger.debug("llm-here not on PATH; using in-tree fallback")
        return None

    override = os.environ.get("CALORON_LLM_PROVIDER", "").strip()
    if override and override not in _LLM_HERE_KNOWN_IDS:
        # Providers caloron's local code knows about but llm-here doesn't
        # (none today; future-proofing). Skip llm-here, fall back.
        logger.debug(
            "CALORON_LLM_PROVIDER=%r not in llm-here registry; falling back",
            override,
        )
        return None

    dangerous = os.environ.get("CALORON_ALLOW_DANGEROUS_CLAUDE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    argv = ["llm-here", "run", "--timeout", str(min(timeout, 300))]
    if override:
        argv.extend(["--provider", override])
    else:
        argv.append("--auto")
    if dangerous:
        argv.append("--dangerous-claude")

    try:
        result = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        # OSError covers FileNotFoundError (PATH race: llm-here was present
        # at `shutil.which` time and gone a millisecond later) and
        # PermissionError (binary on PATH but not executable). Fall back.
        logger.debug("llm-here spawn failed: %s", exc)
        return None

    # llm-here exit codes: 0 = success, 1 = "attempted but failed", 2 =
    # internal error. For 1 we parse the payload below and log the
    # provider's own error; for 2 the stderr is the only diagnostic we
    # have. Both paths fall back to local providers.
    if result.returncode == 2:
        logger.debug(
            "llm-here exit 2 (internal error); stderr=%s; falling back",
            result.stderr.strip(),
        )
        return None
    if result.returncode not in (0, 1):
        logger.debug(
            "llm-here unexpected exit %d; stderr=%s; falling back",
            result.returncode,
            result.stderr.strip(),
        )
        return None

    try:
        payload = _json.loads(result.stdout)
    except _json.JSONDecodeError as exc:
        logger.debug("llm-here emitted invalid JSON: %s; falling back", exc)
        return None

    # Schema-shape defence: a future breaking change or wire corruption
    # could return valid JSON that isn't the documented ``{ok, text,
    # ...}`` object. Refuse rather than raise `AttributeError` on
    # ``payload.get``, which would propagate out of `_call_via_llm_here`
    # and break `call_llm` entirely before the fallback could run.
    if not isinstance(payload, dict):
        logger.debug(
            "llm-here returned non-object JSON (%s); falling back",
            type(payload).__name__,
        )
        return None

    if not payload.get("ok"):
        logger.debug(
            "llm-here reported ok=false; error=%r; falling back",
            payload.get("error"),
        )
        return None

    text = payload.get("text")
    if not isinstance(text, str) or not text:
        logger.debug(
            "llm-here payload ok but text is missing/non-string; falling back"
        )
        return None
    return text


def call_llm(prompt: str, timeout: int = 120) -> str | None:
    """Try every configured provider in order; return the first non-empty result.

    Primary path: delegate to the shared ``llm-here`` binary when
    installed (handles all four subscription CLIs + three APIs with
    bounded timeout, child-kill on expiry, and no key leakage in
    errors).

    Fallback path: the in-tree provider chain below, preserved for
    deployments where ``llm-here`` is not yet installed. This is the
    original implementation; it will be deleted in a follow-up PR once
    llm-here is ubiquitous.

    Set ``CALORON_LLM_SKIP_CLI=1`` to skip subprocess-based providers in
    the auto-chain. Intended for sandboxed environments (like Noether's
    nix executor) where CLI auth state isn't mounted and subprocess
    calls stall. Explicit ``CALORON_LLM_PROVIDER`` always wins.
    """
    # Primary: llm-here (if installed and the override is compatible).
    out = _call_via_llm_here(prompt, timeout)
    if out is not None:
        return out

    # Fallback: in-tree provider chain.
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
