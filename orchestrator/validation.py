"""Request-boundary validation for orchestrator-side IDs and branch names.

Python mirror of `shell/src/validation.rs::is_valid_id`. Any value that
flows into a subprocess argv, a git branch/ref, or a shell-interpolated
string must be validated with one of these helpers before it hits
`subprocess.run` or an f-string constructing a shell script.

## Why not rely on the shell validator alone?

The Rust HTTP shell (`/spawn`, `/heartbeat`) rejects malformed IDs at
the HTTP boundary — that protects the shell's own subprocess calls.
But the Python orchestrator also spawns subprocesses directly
(`subprocess.run(["git", ...])`, `docker exec ... sh -c "<script>"`,
...) without routing through the shell. Those paths bypass the Rust
validator entirely, so the same invariants need to be re-established
here.

## Two patterns, slightly different domains

- **`is_valid_id`** — strict `^[a-z0-9_-]{1,64}$`, identical to
  `shell/src/validation.rs`. Use for `task_id`, `sprint_id`, `agent_id`
  and anything that matches that namespace.
- **`is_valid_branch`** — permissive `^[a-z0-9._/-]{1,128}$`. Git
  branches legitimately use `/` (feature/foo) and `.` (v0.1.0); the
  strict ID pattern is too narrow. Still excludes shell
  metacharacters, whitespace, unicode, and quote characters.

If neither fits, `shlex.quote` is the correct escape hatch for
arbitrary human text (commit messages, PR titles) that gets
interpolated into a shell script.
"""

from __future__ import annotations

import re

_ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
_BRANCH_PATTERN = re.compile(r"^[a-z0-9._/-]{1,128}$")

# Disallowed substrings / leading characters for branch names. The
# character class above permits `.` and `/` individually, which means
# a literal `..` sequence also matches — enough to constitute a
# path-traversal vector when the value flows into a filesystem path
# or URL. Leading `/` would hand git an absolute-looking ref; leading
# `-` would be interpreted as an argv flag by any subprocess callee.
_BRANCH_FORBIDDEN_SUBSTRINGS = ("..",)
_BRANCH_FORBIDDEN_PREFIXES = ("/", "-")


def is_valid_id(value: object) -> bool:
    """True iff `value` is a plain ASCII lowercase id suitable for use as
    a subprocess argument or filesystem component.

    Mirrors `shell/src/validation.rs::is_valid_id`. Length 1-64, charset
    `[a-z0-9_-]`, case-sensitive. Rejects empty strings, anything over
    64 bytes, shell metacharacters, path traversal, absolute paths,
    uppercase, and unicode.
    """
    return isinstance(value, str) and bool(_ID_PATTERN.fullmatch(value))


def is_valid_branch(value: object) -> bool:
    """True iff `value` is suitable for use as a git branch/ref name.

    Permissive vs `is_valid_id`: allows `/` and `.` so branches like
    `feat/foo` and `v0.1.0` pass. Still rejects shell metacharacters,
    whitespace, quote characters, unicode, path-traversal sequences
    (``..``), leading ``/`` (absolute-looking refs), and leading ``-``
    (argv flag hijacks). Length 1-128.

    The pattern alone would accept ``..`` as two adjacent dots — the
    character class permits both — so we explicitly forbid that
    substring. Same reasoning for the leading-character blocklist.

    Note: this is *not* a full git ref-format validator — it's the
    subset caloron actually uses plus a blocklist for dangerous
    characters. See `git-check-ref-format(1)` for the full picture if
    you need to accept wider inputs.
    """
    if not (isinstance(value, str) and _BRANCH_PATTERN.fullmatch(value)):
        return False
    if any(sub in value for sub in _BRANCH_FORBIDDEN_SUBSTRINGS):
        return False
    if value.startswith(_BRANCH_FORBIDDEN_PREFIXES):
        return False
    return True


def require_id(kind: str, value: object) -> str:
    """Raise `ValueError` if `value` is not a valid id; return it otherwise.

    Use at function entry for typed rejection rather than sprinkling
    validation through the call-graph:

        def run_agent_with_supervision(task_id: str, ...):
            require_id("task_id", task_id)
            ...
    """
    if not is_valid_id(value):
        raise ValueError(
            f"invalid {kind}: {value!r} "
            f"(must match ^[a-z0-9_-]{{1,64}}$)"
        )
    # `is_valid_id` just confirmed `value` is a `str`; assert the
    # narrowing explicitly so pyright can see it and we don't need
    # `# type: ignore[return-value]`.
    assert isinstance(value, str)
    return value


def require_branch(kind: str, value: object) -> str:
    """Raise `ValueError` if `value` is not a valid branch name; return it otherwise."""
    if not is_valid_branch(value):
        raise ValueError(
            f"invalid {kind}: {value!r} "
            f"(must match ^[a-z0-9._/-]{{1,128}}$, no '..', "
            f"no leading '/' or '-')"
        )
    # See `require_id` for the assert rationale.
    assert isinstance(value, str)
    return value
