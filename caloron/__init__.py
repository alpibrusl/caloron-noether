"""Caloron — autonomous AI sprint orchestration.

Run sprints, manage projects, track metrics across agent versions.
"""

__version__ = "0.1.0"

from caloron.project.store import ProjectStore, Project
from caloron.metrics.collector import MetricsCollector

__all__ = [
    "Project",
    "ProjectStore",
    "MetricsCollector",
    "__version__",
]
