"""Metrics collector — aggregates KPIs across sprints in a project."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from caloron.project.store import Project, ProjectStore


@dataclass
class ProjectMetrics:
    """Aggregated KPIs across all sprints in a project."""

    total_sprints: int = 0
    total_tasks: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_blocked: int = 0
    avg_clarity: float = 0.0
    avg_sprint_time_s: float = 0.0
    total_supervisor_events: int = 0
    completion_rate: float = 0.0
    total_review_cycles: int = 0
    total_tests_passing: int = 0
    most_common_blockers: list[tuple[str, int]] = field(default_factory=list)
    tools_used: list[tuple[str, int]] = field(default_factory=list)
    sprint_history: list[dict[str, Any]] = field(default_factory=list)


class MetricsCollector:
    """Computes metrics from a project's sprint history."""

    def __init__(self, store: ProjectStore | None = None) -> None:
        self.store = store or ProjectStore()

    def collect(self, project: Project) -> ProjectMetrics:
        """Aggregate metrics across all sprints in a project."""
        sprints = self.store.get_sprints(project)
        if not sprints:
            return ProjectMetrics()

        clarities: list[float] = []
        times: list[int] = []
        blockers_counter: Counter[str] = Counter()
        tools_counter: Counter[str] = Counter()

        m = ProjectMetrics()
        m.total_sprints = len(sprints)

        for s in sprints:
            m.total_tasks += s.get("total_tasks", 0)
            m.total_completed += s.get("completed_tasks", 0)
            m.total_failed += s.get("failed_tasks", 0)
            m.total_blocked += s.get("blocked_tasks", 0)
            m.total_supervisor_events += s.get("supervisor_events", 0)
            m.total_review_cycles += s.get("review_cycles", 0)
            m.total_tests_passing += s.get("tests_passing", 0)

            if "avg_clarity" in s:
                clarities.append(float(s["avg_clarity"]))
            if "sprint_time_s" in s:
                times.append(int(s["sprint_time_s"]))

            for b in s.get("blockers", []):
                blockers_counter[b[:80]] += 1
            for t in s.get("tools_used", []):
                tools_counter[t] += 1

        m.avg_clarity = sum(clarities) / len(clarities) if clarities else 0.0
        m.avg_sprint_time_s = sum(times) / len(times) if times else 0.0
        m.completion_rate = (
            m.total_completed / m.total_tasks if m.total_tasks else 0.0
        )
        m.most_common_blockers = blockers_counter.most_common(5)
        m.tools_used = tools_counter.most_common(10)
        m.sprint_history = sprints

        return m

    def trend(self, project: Project, metric: str = "avg_clarity") -> list[float]:
        """Get a metric's value across all sprints (for trend analysis)."""
        sprints = self.store.get_sprints(project)
        return [float(s.get(metric, 0)) for s in sprints]
