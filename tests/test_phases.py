"""Unit tests for the phase stages (architect_po → dev_po)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow `import stages.phases…` regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stages.phases import (  # noqa: E402
    architect_po,
    dev_po,
    phases_to_sprint_tasks,
    review_po,
)


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
    monkeypatch.setattr(architect_po, "_llm_call", lambda _prompt, timeout=60: canned)
    out = architect_po.execute({"goal": "Build an anomaly pipeline", "constraints": ""})
    names = [c["name"] for c in out["components"]]
    assert names == ["Ingestor", "Ranker"]
    assert "LLM design" in out["design_doc"]
    assert out["risks"] == ["Ingestor could saturate the API."]


def test_architect_falls_back_when_llm_returns_invalid_json(monkeypatch):
    monkeypatch.setattr(architect_po, "_llm_call", lambda _p, timeout=60: "sorry, here's no JSON for you")
    out = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    # Falls back to template — Parser is extracted by the regex heuristic.
    assert "Parser" in [c["name"] for c in out["components"]]


def test_architect_falls_back_when_llm_output_misses_required_fields(monkeypatch):
    bad = '{"design_doc": "x", "components": [{"name": "NoInterface"}]}'
    monkeypatch.setattr(architect_po, "_llm_call", lambda _p, timeout=60: bad)
    out = architect_po.execute({"goal": "Build a Parser", "constraints": ""})
    # Template path kicks in; LLM output is discarded.
    assert out["design_doc"].startswith("# Design")


def test_architect_falls_back_when_llm_returns_none(monkeypatch):
    monkeypatch.setattr(architect_po, "_llm_call", lambda _p, timeout=60: None)
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
    monkeypatch.setattr(dev_po, "_llm_call", lambda _p, timeout=60: canned)
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
    monkeypatch.setattr(dev_po, "_llm_call", lambda _p, timeout=60: canned)
    out = dev_po.execute(
        {
            "components": [{"name": "Parser", "purpose": "p", "interface": "i"}],
            "design_doc": "",
        }
    )
    # Template fallback produces impl-parser/tests-parser, not impl-ghost.
    ids = [t["id"] for t in out["tasks"]]
    assert ids == ["impl-parser", "tests-parser"]


def test_llm_call_returns_none_without_api_key(monkeypatch):
    """Safety check: no key → no call, no exception, None."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert architect_po._llm_call("anything") is None
    assert dev_po._llm_call("anything") is None


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
