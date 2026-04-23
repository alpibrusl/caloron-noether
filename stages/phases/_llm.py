"""Caloron LLM gateway — a thin subprocess shim around ``llm-here``.

Previously this module carried 243 LOC of:

- four CLI subprocess dispatchers (``_claude_cli``, ``_gemini_cli``,
  ``_cursor_cli``, ``_opencode_cli``)
- three HTTP API dispatchers (``_anthropic_api``, ``_openai_api``,
  ``_gemini_api``) with their own request/response shapes
- a fallback chain + provider-override routing

All of that behaviour moved to the shared ``llm-here`` binary
([alpibrusl/llm-here](https://github.com/alpibrusl/llm-here)) in
release v0.3. Caloron was a soft-dep consumer in #22 — this module
kept its in-tree implementation as a fallback so deployments without
llm-here kept working. That fallback is now deleted (Phase 2 of the
llm-here migration).

## Requirements

- ``llm-here`` must be on ``PATH``. Install via ``cargo install llm-here``
  or pick up the release binary from the alpibrusl/llm-here repo.
- At least one of the llm-here-supported providers must be reachable
  (a subscription CLI logged in, or an API key set). ``llm-here
  detect`` enumerates what's available on the current host.

## Caller-visible contract

Unchanged from earlier versions:

``call_llm(prompt, timeout=120) -> str | None``
  Returns the model's text on success, or ``None`` on any failure
  (``llm-here`` missing, provider error, timeout, bad response).
  Callers fall back to deterministic template logic on ``None``.

## Forwarded environment variables

- ``CALORON_LLM_PROVIDER`` — pinned provider id. Must be a value
  ``llm-here`` recognises (``claude-cli``, ``gemini-cli``, …).
  Forwarded as ``--provider <id>``; an unknown id causes ``None``
  return rather than a random fallback, matching prior behaviour
  when providers didn't match ``_DISPATCH``.
- ``CALORON_LLM_SKIP_CLI`` — honoured natively by ``llm-here`` as one
  of four aliases (``LLM_HERE_SKIP_CLI`` /
  ``NOETHER_LLM_SKIP_CLI`` / ``CALORON_LLM_SKIP_CLI`` /
  ``AGENTSPEC_LLM_SKIP_CLI``). We don't explicitly forward — setting
  any of these has the same effect.
- ``CALORON_ALLOW_DANGEROUS_CLAUDE`` — forwarded as
  ``--dangerous-claude`` (enables claude-code's
  ``--dangerously-skip-permissions``). Unset means off.

Every failure path logs a ``logger.debug`` breadcrumb so
``logging.basicConfig(level=logging.DEBUG)`` surfaces *why*
dispatch failed in production.
"""

from __future__ import annotations

import json as _json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Ids ``llm-here`` recognises as of v0.3. Caloron's historical
# ``CALORON_LLM_PROVIDER`` used this same id set; an override outside
# this set returns ``None`` rather than letting an invalid argv leak
# through to ``llm-here run --provider <garbage>``.
_LLM_HERE_KNOWN_IDS = frozenset(
    {
        "claude-cli",
        "gemini-cli",
        "cursor-cli",
        "opencode",
        "anthropic-api",
        "openai-api",
        "gemini-api",
        "mistral-api",
    }
)

# Upper bound we're willing to pass to ``llm-here --timeout``. Prevents
# a caller-supplied ``timeout`` kwarg from stretching the subprocess
# past five minutes regardless of what the llm-here CLI itself tolerates.
_MAX_LLM_HERE_TIMEOUT_S = 300


def call_llm(prompt: str, timeout: int = 120) -> str | None:
    """Dispatch a prompt via ``llm-here``; return the text or ``None``.

    Returns the provider's response text on success, ``None`` on any
    failure:

    - ``llm-here`` not on PATH → ``None``.
    - Requested provider unknown to llm-here → ``None``.
    - Subprocess spawn failure (permission, FS race) → ``None``.
    - llm-here exit code 1 (tried but failed) or 2 (internal error)
      → ``None``.
    - Invalid / non-object / ``ok: false`` JSON from llm-here → ``None``.
    - Missing, non-string, or empty ``text`` field → ``None``.

    Every path logs at DEBUG with the specific reason.
    """
    if not shutil.which("llm-here"):
        logger.debug(
            "llm-here not on PATH; returning None. "
            "Install via `cargo install llm-here` to enable LLM dispatch."
        )
        return None

    override = os.environ.get("CALORON_LLM_PROVIDER", "").strip()
    if override and override not in _LLM_HERE_KNOWN_IDS:
        logger.debug(
            "CALORON_LLM_PROVIDER=%r not in llm-here registry; returning None",
            override,
        )
        return None

    dangerous = os.environ.get("CALORON_ALLOW_DANGEROUS_CLAUDE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    argv = ["llm-here", "run", "--timeout", str(min(timeout, _MAX_LLM_HERE_TIMEOUT_S))]
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
    except (subprocess.TimeoutExpired, OSError) as exc:
        # OSError covers FileNotFoundError (PATH race: llm-here was present
        # at `shutil.which` time and gone a millisecond later) and
        # PermissionError (binary on PATH but not executable).
        logger.debug("llm-here spawn failed: %s", exc)
        return None

    # llm-here exit codes: 0 = success, 1 = "attempted but failed",
    # 2 = internal error. For 1 we parse the payload below and log
    # the provider's own error; for 2 the stderr is the only diagnostic.
    if result.returncode == 2:
        logger.debug(
            "llm-here exit 2 (internal error); stderr=%s",
            result.stderr.strip(),
        )
        return None
    if result.returncode not in (0, 1):
        logger.debug(
            "llm-here unexpected exit %d; stderr=%s",
            result.returncode,
            result.stderr.strip(),
        )
        return None

    try:
        payload = _json.loads(result.stdout)
    except _json.JSONDecodeError as exc:
        logger.debug("llm-here emitted invalid JSON: %s", exc)
        return None

    # Schema-shape defence: a future breaking change or wire corruption
    # could return valid JSON that isn't the documented ``{ok, text, ...}``
    # object. Refuse rather than raise ``AttributeError`` on
    # ``payload.get`` — would propagate out of call_llm and crash the
    # calling phase stage.
    if not isinstance(payload, dict):
        logger.debug(
            "llm-here returned non-object JSON (%s); returning None",
            type(payload).__name__,
        )
        return None

    if not payload.get("ok"):
        logger.debug(
            "llm-here reported ok=false; error=%r",
            payload.get("error"),
        )
        return None

    text = payload.get("text")
    if not isinstance(text, str) or not text:
        logger.debug("llm-here payload ok but text is missing / non-string / empty")
        return None
    return text
