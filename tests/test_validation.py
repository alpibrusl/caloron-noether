"""Tests for orchestrator.validation — Python mirror of the shell's is_valid_id.

Parallels `shell/src/validation.rs::tests` one-for-one where the
pattern is identical, and adds branch-specific cases for the
permissive variant.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orchestrator.validation import (  # noqa: E402
    is_valid_branch,
    is_valid_id,
    require_branch,
    require_id,
)

# ── is_valid_id — should match shell/src/validation.rs 1:1 ────────────────────


class TestIsValidId:
    def test_accepts_plain_ids(self):
        for good in ["agent-001", "sprint_2026_04", "po", "a", "x" * 64]:
            assert is_valid_id(good), good

    def test_rejects_empty(self):
        assert not is_valid_id("")

    def test_rejects_over_64(self):
        assert not is_valid_id("x" * 65)
        assert not is_valid_id("x" * 1000)

    def test_rejects_path_traversal(self):
        for bad in ["../../../etc/passwd", "..", "a/b", "./foo"]:
            assert not is_valid_id(bad), bad

    def test_rejects_absolute_paths(self):
        assert not is_valid_id("/etc/passwd")
        assert not is_valid_id("/")

    def test_rejects_shell_metacharacters(self):
        for bad in [
            "a;b", "a|b", "a&b", "a$b", "a`b", "a b", "a\tb",
            "a\nb", "a'b", "a\"b", "a\\b",
        ]:
            assert not is_valid_id(bad), f"should reject {bad!r}"

    def test_rejects_uppercase(self):
        assert not is_valid_id("Agent-1")
        assert not is_valid_id("PO")

    def test_rejects_unicode(self):
        assert not is_valid_id("agént")
        assert not is_valid_id("\u202egnp")  # right-to-left override

    def test_rejects_non_strings(self):
        for bad in [None, 42, [], {}, b"agent-001"]:
            assert not is_valid_id(bad), f"should reject {bad!r}"


# ── is_valid_branch — permissive for git semantics ────────────────────────────


class TestIsValidBranch:
    def test_accepts_simple_branches(self):
        for good in ["main", "feat/foo", "v0.1.0", "agent/task-001", "release-2026-04-21"]:
            assert is_valid_branch(good), good

    def test_accepts_any_valid_id(self):
        # Every valid id must also be a valid branch (strict ⊂ permissive).
        for good in ["agent-001", "po", "a", "x" * 64]:
            assert is_valid_branch(good), good

    def test_accepts_up_to_128_chars(self):
        assert is_valid_branch("x" * 128)

    def test_rejects_over_128(self):
        assert not is_valid_branch("x" * 129)

    def test_rejects_empty(self):
        assert not is_valid_branch("")

    def test_rejects_shell_metacharacters(self):
        for bad in [
            "feat;rm", "foo|bar", "foo$bar", "foo`cmd`", "foo(cmd)",
            "a b", "a\tb", "a\nb", "a'b", "a\"b", "a\\b",
        ]:
            assert not is_valid_branch(bad), f"should reject {bad!r}"

    def test_rejects_uppercase(self):
        # Git branches are technically case-insensitive on some filesystems
        # but caloron's own branches are always lowercase by convention.
        # Tightening here prevents surprise on case-folding filesystems.
        assert not is_valid_branch("Main")
        assert not is_valid_branch("FEAT/foo")

    def test_rejects_unicode(self):
        assert not is_valid_branch("fóo")
        assert not is_valid_branch("\u202efoo")

    def test_rejects_path_traversal(self):
        # The character class `[a-z0-9._/-]` accepts `.` and `/`
        # individually, so a `..` sequence passes the regex. An
        # explicit substring blocklist closes that gap. Regression
        # guard for the bug caught in the PR #24 review.
        for bad in [
            "../etc/passwd",
            "..",
            "foo/../bar",
            "a/../../b",
            "../../secret",
            "foo..bar",  # inline `..` without slashes
            "..foo",  # leading
            "foo..",  # trailing
        ]:
            assert not is_valid_branch(bad), f"should reject {bad!r}"

    def test_rejects_leading_slash(self):
        # An absolute-looking ref flips `git fetch` semantics.
        for bad in ["/main", "/etc/passwd", "/"]:
            assert not is_valid_branch(bad), f"should reject {bad!r}"

    def test_rejects_leading_dash(self):
        # argv flag hijack: `git merge -rf` etc. A trailing dash is
        # fine; only leading is forbidden.
        for bad in ["-rf", "--force", "-delete"]:
            assert not is_valid_branch(bad), f"should reject {bad!r}"
        # Legitimate use of dashes internally/at end still passes.
        assert is_valid_branch("feat-abc")
        assert is_valid_branch("abc-")


# ── require_* — typed rejection helpers ───────────────────────────────────────


class TestRequireHelpers:
    def test_require_id_returns_on_success(self):
        assert require_id("task_id", "task-001") == "task-001"

    def test_require_id_raises_with_kind_in_message(self):
        with pytest.raises(ValueError, match="invalid task_id"):
            require_id("task_id", "Invalid Task!")

    def test_require_id_raises_on_non_string(self):
        with pytest.raises(ValueError, match="invalid task_id"):
            require_id("task_id", None)  # type: ignore[arg-type]

    def test_require_branch_returns_on_success(self):
        assert require_branch("branch", "feat/foo") == "feat/foo"

    def test_require_branch_raises_with_kind_in_message(self):
        with pytest.raises(ValueError, match="invalid branch"):
            require_branch("branch", "feat;rm -rf /")

    def test_require_branch_mentions_traversal_constraint_in_message(self):
        # The error message lists the rules — when a traversal
        # substring triggers the rejection, the operator should see
        # the explicit `no '..'` cue, not just the pattern.
        with pytest.raises(ValueError, match="no '\\.\\.'"):
            require_branch("branch", "../etc/passwd")

    def test_require_message_includes_offending_value(self):
        # Defensive for debuggability: the raised error must include the
        # offending value so operators can see what was wrong. Use repr()
        # so shell metacharacters don't re-activate when the message is
        # printed to a shell.
        with pytest.raises(ValueError, match="'bad\\$value'"):
            require_id("task_id", "bad$value")
