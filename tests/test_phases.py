"""Unit tests for the phase stages (architect_po → dev_po)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow `import stages.phases…` regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stages.phases import (  # noqa: E402
    architect_po,
    design_po,
    dev_po,
    phases_to_sprint_tasks,
    review_po,
)


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """Disable LLM calls by default so tests don't hit real providers.

    Tests that want the LLM path monkeypatch call_llm explicitly; this
    fixture makes everything else deterministic and fast.
    """
    monkeypatch.setattr(architect_po, "call_llm", lambda _p, timeout=120: None)
    monkeypatch.setattr(dev_po, "call_llm", lambda _p, timeout=120: None)


def _validate_arch_shape(out: dict) -> None:
    """Assert the architect output matches the phase-boundary schema."""
    for key in ("design_doc", "components", "risks"):
        assert key in out, f"missing {key}"
    assert isinstance(out["components"], list) and out["components"], "need components"
    for c in out["components"]:
        assert {"name", "purpose", "interface"} <= c.keys(), c

# ── architect_po ─────────────────────────────────────────────────────────────


def test_architect_rejects_empty_goal():
    with pytest.raises(ValueError, match="non-empty"):
        architect_po.execute({"goal": "", "constraints": ""})


def test_architect_identifies_capitalised_nouns():
    out = architect_po.execute(
        {
            "goal": "Build a RateMonitor and an AnomalyDetector to flag outliers.",
            "constraints": "",
        }
    )
    names = [c["name"] for c in out["components"]]
    assert "RateMonitor" in names
    assert "AnomalyDetector" in names
    assert out["design_doc"].startswith("# Design — ")


def test_architect_falls_back_to_core_component():
    out = architect_po.execute({"goal": "do the thing", "constraints": ""})
    assert [c["name"] for c in out["components"]] == ["Core"]
    assert out["risks"]  # single-component risk was surfaced


def test_architect_output_matches_phase_boundary_schema():
    out = architect_po.execute(
        {"goal": "Build a Parser and Validator", "constraints": "Linux only"}
    )
    _validate_arch_shape(out)


# ── dev_po ───────────────────────────────────────────────────────────────────


def _arch_fixture() -> dict:
    return {
        "design_doc": "# doc",
        "components": [
            {"name": "Parser", "purpose": "Parse input", "interface": "parse(s)->AST"},
            {"name": "Validator", "purpose": "Validate", "interface": "validate(ast)->bool"},
        ],
        "risks": [],
    }


def test_dev_emits_impl_and_tests_per_component():
    arch = _arch_fixture()
    out = dev_po.execute({"components": arch["components"], "sprint_id": "s1"})
    ids = [t["id"] for t in out["tasks"]]
    assert ids == ["impl-parser", "tests-parser", "impl-validator", "tests-validator"]
    # tests depend on impl
    for t in out["tasks"]:
        if t["id"].startswith("tests-"):
            assert t["depends_on"] == [t["id"].replace("tests-", "impl-")]


def test_dev_propagates_framework():
    arch = _arch_fixture()
    out = dev_po.execute(
        {"components": arch["components"], "sprint_id": "s1", "framework": "gemini-cli"}
    )
    assert all(t["framework"] == "gemini-cli" for t in out["tasks"])


def test_dev_rejects_missing_components():
    with pytest.raises(ValueError, match="non-empty"):
        dev_po.execute({"components": [], "sprint_id": "s1"})


# ── End-to-end: architect → dev chain ────────────────────────────────────────


def test_full_cycle_chain():
    arch_out = architect_po.execute(
        {
            "goal": "Build a DataLoader and a ModelTrainer with checkpointing.",
            "constraints": "",
        }
    )
    dev_out = dev_po.execute(
        {
            "components": arch_out["components"],
            "sprint_id": "e2e",
            "framework": "claude-code",
        }
    )
    # Every component yields two tasks (impl + tests).
    assert len(dev_out["tasks"]) == 2 * len(arch_out["components"])
    # Traceability back to component is preserved.
    component_names = {c["name"] for c in arch_out["components"]}
    assert {t["component"] for t in dev_out["tasks"]} == component_names


# ── review_po ────────────────────────────────────────────────────────────────


def test_review_rejects_empty_tasks():
    with pytest.raises(ValueError, match="non-empty"):
        review_po.execute({"tasks": [], "design_doc": "", "framework": "claude-code"})


def test_review_emits_one_check_per_task_with_dependency():
    arch = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    dev = dev_po.execute({"components": arch["components"], "sprint_id": "s1"})
    rev = review_po.execute(
        {"tasks": dev["tasks"], "design_doc": arch["design_doc"], "framework": "claude-code"}
    )
    checks = rev["review_checks"]
    assert len(checks) == len(dev["tasks"])
    for task, check in zip(dev["tasks"], checks, strict=True):
        assert check["reviews"] == task["id"]
        assert check["id"] == f"review-{task['id']}"


def test_review_distinguishes_impl_from_tests_focus():
    arch = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    dev = dev_po.execute({"components": arch["components"], "sprint_id": "s1"})
    rev = review_po.execute(
        {"tasks": dev["tasks"], "design_doc": arch["design_doc"], "framework": "claude-code"}
    )
    impl_foci = {c["focus"] for c in rev["review_checks"] if c["reviews"].startswith("impl-")}
    tests_foci = {c["focus"] for c in rev["review_checks"] if c["reviews"].startswith("tests-")}
    assert impl_foci and tests_foci and impl_foci.isdisjoint(tests_foci)


# ── design_po (no-op pass-through) ──────────────────────────────────────────


def test_design_rejects_empty_goal():
    with pytest.raises(ValueError, match="non-empty"):
        design_po.execute({"goal": "", "constraints": ""})


def test_design_passes_through_goal_and_constraints():
    out = design_po.execute({"goal": "Build an anomaly dashboard", "constraints": "Desktop only"})
    assert out["goal"] == "Build an anomaly dashboard"
    assert out["constraints"] == "Desktop only"


def test_design_provides_empty_artifact_slots_when_absent():
    out = design_po.execute({"goal": "x", "constraints": ""})
    assert out["design_brief"] == ""
    assert out["components_inventory"] == []


def test_design_preserves_upstream_artifacts():
    """If an earlier stage (or the input) already supplied design artifacts, keep them."""
    out = design_po.execute(
        {
            "goal": "x",
            "constraints": "y",
            "design_brief": "Users must feel calm.",
            "components_inventory": [{"name": "Table", "purpose": "show things"}],
        }
    )
    assert out["design_brief"] == "Users must feel calm."
    assert out["components_inventory"] == [{"name": "Table", "purpose": "show things"}]


def test_design_feeds_into_architect():
    """End-to-end: design_po → architect_po chain works via structural subtyping."""
    design_out = design_po.execute(
        {"goal": "Build a Parser and Validator", "constraints": ""}
    )
    arch_out = architect_po.execute(design_out)
    # Architect still gets its job done — design_po's extra fields don't break it.
    assert arch_out["design_doc"]
    assert arch_out["components"]


# ── LLM path (mocked) ────────────────────────────────────────────────────────


def test_architect_uses_llm_output_when_schema_valid(monkeypatch):
    """Happy path: LLM returns well-formed JSON, stage trusts it."""
    canned = (
        "Here's the plan:\n"
        '{"design_doc": "# LLM design\\n\\nDetailed markdown doc.", '
        '"components": ['
        '{"name": "Ingestor", "purpose": "Pull records", "interface": "ingest()"}, '
        '{"name": "Ranker", "purpose": "Score records", "interface": "rank(list) -> list"}'
        '], "risks": ["Ingestor could saturate the API."]}'
    )
    monkeypatch.setattr(architect_po, "call_llm", lambda _prompt, timeout=120: canned)
    out = architect_po.execute({"goal": "Build an anomaly pipeline", "constraints": ""})
    names = [c["name"] for c in out["components"]]
    assert names == ["Ingestor", "Ranker"]
    assert "LLM design" in out["design_doc"]
    assert out["risks"] == ["Ingestor could saturate the API."]


def test_architect_falls_back_when_llm_returns_invalid_json(monkeypatch):
    monkeypatch.setattr(architect_po, "call_llm", lambda _p, timeout=120: "sorry, here's no JSON for you")
    out = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    # Falls back to template — Parser is extracted by the regex heuristic.
    assert "Parser" in [c["name"] for c in out["components"]]


def test_architect_falls_back_when_llm_output_misses_required_fields(monkeypatch):
    bad = '{"design_doc": "x", "components": [{"name": "NoInterface"}]}'
    monkeypatch.setattr(architect_po, "call_llm", lambda _p, timeout=120: bad)
    out = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    # Template path kicks in; LLM output is discarded.
    assert out["design_doc"].startswith("# Design")


def test_architect_falls_back_when_llm_returns_none(monkeypatch):
    monkeypatch.setattr(architect_po, "call_llm", lambda _p, timeout=120: None)
    out = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    assert "Parser" in [c["name"] for c in out["components"]]


def test_dev_uses_llm_tasks_when_schema_valid(monkeypatch):
    canned = (
        '{"tasks": ['
        '{"id": "impl-parser", "title": "Implement Parser", "depends_on": [], '
        '"agent_prompt": "Create src/parser.py with parse(text) -> AST...", '
        '"framework": "claude-code", "component": "Parser"},'
        '{"id": "tests-parser", "title": "Tests for Parser", "depends_on": ["impl-parser"], '
        '"agent_prompt": "Cover parse() happy path + edge cases.", '
        '"framework": "claude-code", "component": "Parser"}'
        ']}'
    )
    monkeypatch.setattr(dev_po, "call_llm", lambda _p, timeout=120: canned)
    out = dev_po.execute(
        {
            "components": [
                {"name": "Parser", "purpose": "Parse", "interface": "parse()"}
            ],
            "design_doc": "# doc",
        }
    )
    assert [t["id"] for t in out["tasks"]] == ["impl-parser", "tests-parser"]
    assert "parse(text)" in out["tasks"][0]["agent_prompt"]


def test_dev_falls_back_when_llm_references_unknown_component(monkeypatch):
    """Schema guard rejects LLM outputs that invent components."""
    canned = (
        '{"tasks": [{"id": "impl-ghost", "title": "Implement Ghost", '
        '"depends_on": [], "agent_prompt": "do it", "component": "Ghost"}]}'
    )
    monkeypatch.setattr(dev_po, "call_llm", lambda _p, timeout=120: canned)
    out = dev_po.execute(
        {
            "components": [{"name": "Parser", "purpose": "p", "interface": "i"}],
            "design_doc": "",
        }
    )
    # Template fallback produces impl-parser/tests-parser, not impl-ghost.
    ids = [t["id"] for t in out["tasks"]]
    assert ids == ["impl-parser", "tests-parser"]


def test_call_llm_returns_none_when_llm_here_not_installed(monkeypatch):
    """Without ``llm-here`` on PATH, ``call_llm`` returns ``None`` — no
    fallback path remains after Phase 2 of the llm-here migration.
    Callers (PO phases) are expected to downgrade to deterministic
    template logic."""
    from stages.phases import _llm

    monkeypatch.delenv("CALORON_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(_llm.shutil, "which", lambda _cmd: None)
    assert _llm.call_llm("anything") is None


# ── llm-here delegation ───────────────────────────────────


def _mock_llm_here_on_path(monkeypatch, _llm):
    """Pretend ``llm-here`` is installed — leave other binaries to the
    real ``shutil.which`` so tests don't accidentally depend on a
    specific host's PATH state."""
    real_which = _llm.shutil.which

    def which(cmd):
        if cmd == "llm-here":
            return "/usr/local/bin/llm-here"
        return real_which(cmd)

    monkeypatch.setattr(_llm.shutil, "which", which)


class _MockSubprocessResult:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_call_llm_prefers_llm_here_when_installed(monkeypatch):
    """When ``llm-here`` is on PATH, call_llm dispatches through it
    instead of falling through to the in-tree provider chain."""
    from stages.phases import _llm

    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _MockSubprocessResult(
            returncode=0,
            stdout='{"schema_version": 1, "ok": true, "text": "via llm-here", "provider_used": "claude-cli"}',
        )

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(_llm.subprocess, "run", fake_run)

    assert _llm.call_llm("hi") == "via llm-here"
    assert len(calls) == 1
    assert calls[0][:2] == ["llm-here", "run"]
    assert "--auto" in calls[0]


def test_call_llm_forwards_provider_override_to_llm_here(monkeypatch):
    """``CALORON_LLM_PROVIDER=claude-cli`` becomes ``--provider claude-cli``
    on the llm-here argv — not ``--auto``."""
    from stages.phases import _llm

    argv_seen: list[str] = []

    def fake_run(argv, **kwargs):
        argv_seen.extend(argv)
        return _MockSubprocessResult(
            returncode=0,
            stdout='{"ok": true, "text": "ok"}',
        )

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setenv("CALORON_LLM_PROVIDER", "claude-cli")
    monkeypatch.setattr(_llm.subprocess, "run", fake_run)

    _llm.call_llm("hi")

    assert "--provider" in argv_seen
    # The id string is adjacent to --provider.
    idx = argv_seen.index("--provider")
    assert argv_seen[idx + 1] == "claude-cli"
    assert "--auto" not in argv_seen


def test_call_llm_forwards_dangerous_claude_flag(monkeypatch):
    """``CALORON_ALLOW_DANGEROUS_CLAUDE=1`` becomes ``--dangerous-claude``
    on the llm-here argv. Same env-var gate caloron has used since v0.4."""
    from stages.phases import _llm

    argv_seen: list[str] = []

    def fake_run(argv, **kwargs):
        argv_seen.extend(argv)
        return _MockSubprocessResult(
            returncode=0,
            stdout='{"ok": true, "text": "ok"}',
        )

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setenv("CALORON_ALLOW_DANGEROUS_CLAUDE", "1")
    monkeypatch.setattr(_llm.subprocess, "run", fake_run)

    _llm.call_llm("hi")

    assert "--dangerous-claude" in argv_seen


def test_call_llm_does_not_forward_dangerous_claude_when_unset(monkeypatch):
    """Default behaviour: ``--dangerous-claude`` is off unless the env
    var is explicitly truthy."""
    from stages.phases import _llm

    argv_seen: list[str] = []

    def fake_run(argv, **kwargs):
        argv_seen.extend(argv)
        return _MockSubprocessResult(
            returncode=0,
            stdout='{"ok": true, "text": "ok"}',
        )

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.delenv("CALORON_ALLOW_DANGEROUS_CLAUDE", raising=False)
    monkeypatch.setattr(_llm.subprocess, "run", fake_run)

    _llm.call_llm("hi")

    assert "--dangerous-claude" not in argv_seen


def test_call_llm_returns_none_when_llm_here_exits_non_zero(monkeypatch):
    """``llm-here run`` exit 1 means "tried but failed". Phase 2 has no
    in-tree fallback — ``call_llm`` returns ``None``."""
    from stages.phases import _llm

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(
        _llm.subprocess,
        "run",
        lambda *a, **k: _MockSubprocessResult(returncode=1, stdout=""),
    )

    assert _llm.call_llm("hi") is None


def test_call_llm_returns_none_when_llm_here_returns_bad_json(monkeypatch):
    """Defensive: malformed llm-here output doesn't crash; returns None."""
    from stages.phases import _llm

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(
        _llm.subprocess,
        "run",
        lambda *a, **k: _MockSubprocessResult(returncode=0, stdout="not json"),
    )
    assert _llm.call_llm("hi") is None


def test_call_llm_returns_none_when_llm_here_reports_ok_false(monkeypatch):
    """``ok: false`` in the llm-here payload → ``None``."""
    from stages.phases import _llm

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(
        _llm.subprocess,
        "run",
        lambda *a, **k: _MockSubprocessResult(
            returncode=0,
            stdout='{"ok": false, "text": null, "error": "no providers reachable"}',
        ),
    )
    assert _llm.call_llm("hi") is None


def test_call_llm_returns_none_on_llm_here_subprocess_timeout(monkeypatch):
    """If the llm-here subprocess times out, ``call_llm`` catches the
    ``TimeoutExpired`` and returns ``None`` — no unhandled exception."""
    from stages.phases import _llm

    def timing_out(*_a, **_k):
        raise _llm.subprocess.TimeoutExpired(cmd=["llm-here"], timeout=5)

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(_llm.subprocess, "run", timing_out)
    assert _llm.call_llm("hi") is None


# Review-comment response carry-over: each of these pins a defence
# the code has for wire-shape edge cases. Originally covered the
# fallback path in #22 review; Phase 2 keeps the defences but the
# outcome is ``None`` instead of fallback text.


@pytest.mark.parametrize("payload", ["[]", "null", "42", '"string"', '"null"'])
def test_call_llm_returns_none_on_non_object_json(monkeypatch, payload):
    """Valid JSON that isn't a dict (e.g. a future schema change or wire
    corruption) must return ``None`` without raising ``AttributeError``
    on ``payload.get(...)``. Mirrors the same defence in agentspec's
    resolver."""
    from stages.phases import _llm

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(
        _llm.subprocess,
        "run",
        lambda *a, **k: _MockSubprocessResult(returncode=0, stdout=payload),
    )
    # Key: no exception escapes; call_llm returns None cleanly.
    assert _llm.call_llm("hi") is None


@pytest.mark.parametrize(
    "payload",
    [
        '{"ok": true, "text": null}',
        '{"ok": true, "text": ""}',
        '{"ok": true, "text": 42}',
        '{"ok": true, "text": ["array", "of", "strings"]}',
        '{"ok": true}',  # text key missing entirely
    ],
)
def test_call_llm_returns_none_on_malformed_text_field(monkeypatch, payload):
    """``ok: true`` with ``text`` missing / wrong-type / empty must return
    ``None``. Locks in the ``isinstance(text, str) and text`` guard so a
    future simplification can't drop it."""
    from stages.phases import _llm

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setattr(
        _llm.subprocess,
        "run",
        lambda *a, **k: _MockSubprocessResult(returncode=0, stdout=payload),
    )
    assert _llm.call_llm("hi") is None


def test_call_llm_does_not_forward_unknown_provider_override_to_llm_here(
    monkeypatch,
):
    """``CALORON_LLM_PROVIDER=<unknown>`` must **not** spawn llm-here
    with a bogus ``--provider <unknown>`` argv. Load-bearing invariant:
    ``llm-here`` never sees an id it doesn't recognise."""
    from stages.phases import _llm

    spawn_calls: list[list[str]] = []

    _mock_llm_here_on_path(monkeypatch, _llm)
    monkeypatch.setenv("CALORON_LLM_PROVIDER", "not-a-real-provider-id")
    monkeypatch.setattr(
        _llm.subprocess,
        "run",
        lambda argv, **k: spawn_calls.append(argv)
        or _MockSubprocessResult(returncode=0, stdout="unused"),
    )

    # Unknown override → None return. The load-bearing assertion is
    # that llm-here was not invoked at all — not that we got None back
    # (we'd get None for many reasons; this test is specifically about
    # the short-circuit before the subprocess spawn).
    assert _llm.call_llm("hi") is None
    assert spawn_calls == [], (
        f"llm-here should not have been invoked for an unknown provider "
        f"id, got argv={spawn_calls}"
    )


# ── Original review_po test (unchanged) ──────────────────────────────────────


def test_review_prompt_embeds_design_doc():
    rev = review_po.execute(
        {
            "tasks": [{"id": "impl-foo", "title": "Implement foo"}],
            "design_doc": "SENTINEL-DESIGN-TOKEN",
            "framework": "claude-code",
        }
    )
    assert "SENTINEL-DESIGN-TOKEN" in rev["review_checks"][0]["agent_prompt"]


def test_dev_carries_arch_fields_through():
    arch = architect_po.execute({"goal": "Build a Parser", "constraints": "Linux only"})
    dev = dev_po.execute({**arch, "sprint_id": "s1"})
    # These must survive so review_po + flatten can consume them downstream.
    assert dev["design_doc"] == arch["design_doc"]
    assert dev["components"] == arch["components"]
    assert dev["risks"] == arch["risks"]


def test_review_preserves_tasks_and_design_doc():
    arch = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    dev = dev_po.execute({**arch, "sprint_id": "s1"})
    rev = review_po.execute({**dev, "framework": "claude-code"})
    assert rev["design_doc"] == arch["design_doc"]
    assert rev["tasks"] == dev["tasks"]


# ── phases_to_sprint_tasks (terminal flatten) ────────────────────────────────


def test_flatten_requires_tasks():
    with pytest.raises(ValueError, match="non-empty"):
        phases_to_sprint_tasks.execute({"tasks": [], "review_checks": [], "design_doc": ""})


def test_flatten_merges_reviews_with_depends_on_wiring():
    arch = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    dev = dev_po.execute({**arch, "sprint_id": "s1"})
    rev = review_po.execute({**dev, "framework": "claude-code"})
    flat = phases_to_sprint_tasks.execute(rev)

    ids = [t["id"] for t in flat["tasks"]]
    # Dev tasks come first, review tasks after.
    assert ids[: len(dev["tasks"])] == [t["id"] for t in dev["tasks"]]
    review_tasks = flat["tasks"][len(dev["tasks"]) :]
    assert len(review_tasks) == len(rev["review_checks"])
    for rt, check in zip(review_tasks, rev["review_checks"], strict=True):
        assert rt["depends_on"] == [check["reviews"]]
        assert rt["id"] == check["id"]
        assert rt["agent_prompt"] == check["agent_prompt"]


def test_flatten_rejects_id_collisions():
    with pytest.raises(ValueError, match="duplicate task id"):
        phases_to_sprint_tasks.execute(
            {
                "tasks": [{"id": "shared", "title": "T"}],
                "review_checks": [
                    {
                        "id": "shared",
                        "reviews": "shared",
                        "focus": "x",
                        "agent_prompt": "p",
                        "framework": "claude-code",
                    }
                ],
                "design_doc": "",
            }
        )


def test_full_cycle_with_flatten_is_orchestrator_compatible():
    """End-to-end: the full graph's terminal output matches --graph's contract."""
    arch = architect_po.execute(
        {"goal": "Build a DataLoader and a ModelTrainer", "constraints": ""}
    )
    dev = dev_po.execute({**arch, "sprint_id": "e2e"})
    rev = review_po.execute({**dev, "framework": "claude-code"})
    final = phases_to_sprint_tasks.execute(rev)

    assert set(final.keys()) == {"tasks"}
    for task in final["tasks"]:
        assert "id" in task
        assert "title" in task
        assert "depends_on" in task
        assert "agent_prompt" in task
