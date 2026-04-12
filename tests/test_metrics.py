"""Tests for the metrics collector."""

from __future__ import annotations

from pathlib import Path

from caloron.metrics.collector import MetricsCollector
from caloron.project.store import ProjectStore


def test_empty_metrics(tmp_caloron_home: Path):
    store = ProjectStore()
    project = store.create("empty")
    m = MetricsCollector(store).collect(project)

    assert m.total_sprints == 0
    assert m.total_tasks == 0
    assert m.avg_clarity == 0.0
    assert m.completion_rate == 0.0


def test_aggregate_across_sprints(tmp_caloron_home: Path):
    store = ProjectStore()
    project = store.create("real")

    store.add_sprint(project, {
        "completed_tasks": 2, "total_tasks": 3, "failed_tasks": 1,
        "avg_clarity": 7.0, "sprint_time_s": 100,
        "blockers": ["pip install failed"], "tools_used": ["pandas"],
    })
    store.add_sprint(project, {
        "completed_tasks": 3, "total_tasks": 3, "failed_tasks": 0,
        "avg_clarity": 9.0, "sprint_time_s": 200,
        "blockers": ["pip install failed"], "tools_used": ["pandas", "fastapi"],
    })

    m = MetricsCollector(store).collect(project)

    assert m.total_sprints == 2
    assert m.total_tasks == 6
    assert m.total_completed == 5
    assert m.total_failed == 1
    assert m.avg_clarity == 8.0
    assert m.avg_sprint_time_s == 150.0
    assert abs(m.completion_rate - 5/6) < 0.01

    blocker_dict = dict(m.most_common_blockers)
    assert blocker_dict.get("pip install failed") == 2

    tools_dict = dict(m.tools_used)
    assert tools_dict.get("pandas") == 2
    assert tools_dict.get("fastapi") == 1


def test_trend(tmp_caloron_home: Path):
    store = ProjectStore()
    project = store.create("trending")
    for clarity in [3.0, 5.0, 8.0]:
        store.add_sprint(project, {"avg_clarity": clarity})
    trend = MetricsCollector(store).trend(project, "avg_clarity")
    assert trend == [3.0, 5.0, 8.0]
