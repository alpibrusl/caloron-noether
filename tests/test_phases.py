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
from stages.phases.phase_schemas import ArchitectOutput, Component  # noqa: E402

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


def test_architect_output_roundtrips_through_schema():
    out = architect_po.execute(
        {"goal": "Build a Parser and Validator", "constraints": "Linux only"}
    )
    ArchitectOutput.from_dict(out)  # raises on schema drift


# ── dev_po ───────────────────────────────────────────────────────────────────


def _arch_fixture() -> dict:
    return ArchitectOutput(
        design_doc="# doc",
        components=[
            Component(name="Parser", purpose="Parse input", interface="parse(s)->AST"),
            Component(name="Validator", purpose="Validate", interface="validate(ast)->bool"),
        ],
    ).to_dict()


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
