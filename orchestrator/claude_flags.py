"""Helper for gating ``claude --dangerously-skip-permissions``.

The flag disables Claude Code's own permission prompts, so the spawned
agent can read, write, and execute anything the process can. For an
orchestrator where DAG content drives prompt content, that is a lot of
trust to extend by default.

We therefore require an explicit opt-in via ``CALORON_ALLOW_DANGEROUS_CLAUDE``
before any call site passes the flag. Treat this like ``sudo`` — it is
reasonable for single-tenant dev and for trusted-DAG workflows, but
unreasonable as an invisible default.
"""

from __future__ import annotations

import os

ENV_VAR = "CALORON_ALLOW_DANGEROUS_CLAUDE"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def dangerous_enabled() -> bool:
    """Return True iff the operator explicitly opted in via env var."""
    return os.environ.get(ENV_VAR, "").strip().lower() in _TRUTHY


def dangerous_flags() -> list[str]:
    """Return the argv fragment to inject after ``claude``.

    Empty list when the env var is unset/falsy; ``["--dangerously-skip-permissions"]``
    when explicitly enabled. Build the full argv as
    ``["claude", *dangerous_flags(), "-p", prompt]``.
    """
    return ["--dangerously-skip-permissions"] if dangerous_enabled() else []
