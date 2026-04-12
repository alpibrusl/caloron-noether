"""Tests for the project store."""

from __future__ import annotations

from pathlib import Path

import pytest
from caloron.project.store import ProjectStore


def test_create_project(tmp_caloron_home: Path):
    store = ProjectStore()
    project = store.create("my-test", repo="gitea://localhost/test/repo")

    assert project.name == "my-test"
    assert project.repo == "gitea://localhost/test/repo"
    assert project.backend == "direct"
    assert project.framework == "claude-code"
    assert project.config_path.exists()
    assert project.sprints_path.exists()
    assert project.profiles_dir.exists()
    assert project.agents_dir.exists()


def test_create_duplicate_raises(tmp_caloron_home: Path):
    store = ProjectStore()
    store.create("dupe")
    with pytest.raises(FileExistsError):
        store.create("dupe")


def test_invalid_name_raises(tmp_caloron_home: Path):
    store = ProjectStore()
    with pytest.raises(ValueError):
        store.create("with/slash")
    with pytest.raises(ValueError):
        store.create(".starts-with-dot")
    with pytest.raises(ValueError):
        store.create("")


def test_first_project_becomes_active(tmp_caloron_home: Path):
    store = ProjectStore()
    store.create("first")
    assert store.get_active() == "first"


def test_switch_active(tmp_caloron_home: Path):
    store = ProjectStore()
    store.create("a")
    store.create("b")
    assert store.get_active() == "a"
    store.set_active("b")
    assert store.get_active() == "b"


def test_switch_unknown_raises(tmp_caloron_home: Path):
    store = ProjectStore()
    with pytest.raises(FileNotFoundError):
        store.set_active("ghost")


def test_list(tmp_caloron_home: Path):
    store = ProjectStore()
    assert store.list() == []
    store.create("alpha")
    store.create("beta")
    names = [p.name for p in store.list()]
    assert names == ["alpha", "beta"]


def test_delete(tmp_caloron_home: Path):
    store = ProjectStore()
    store.create("temp")
    assert store.delete("temp") is True
    assert store.delete("temp") is False
    assert store.get("temp") is None


def test_delete_clears_active(tmp_caloron_home: Path):
    store = ProjectStore()
    store.create("only")
    assert store.get_active() == "only"
    store.delete("only")
    assert store.get_active() is None


def test_add_and_get_sprint(tmp_caloron_home: Path):
    store = ProjectStore()
    project = store.create("sprintable")

    sid = store.add_sprint(project, {
        "goal": "test goal",
        "completed_tasks": 3,
        "total_tasks": 3,
        "avg_clarity": 8.5,
    })
    assert sid == 1

    sprints = store.get_sprints(project)
    assert len(sprints) == 1
    assert sprints[0]["sprint_id"] == 1
    assert sprints[0]["goal"] == "test goal"
    assert "completed_at" in sprints[0]

    # Add another
    sid2 = store.add_sprint(project, {"goal": "second"})
    assert sid2 == 2

    fetched = store.get_sprint(project, 1)
    assert fetched is not None
    assert fetched["goal"] == "test goal"

    assert store.get_sprint(project, 99) is None
