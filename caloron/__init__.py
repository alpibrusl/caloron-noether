"""Caloron — autonomous AI sprint orchestration.

Run sprints, manage projects, track metrics across agent versions.
"""

__version__ = "0.4.1"

from caloron.metrics.collector import MetricsCollector
from caloron.project.store import Project, ProjectStore

__all__ = [
    "Project",
    "ProjectStore",
    "MetricsCollector",
    "__version__",
]
