"""Project store — persistent state for caloron projects.

Each project has its own directory at ~/.caloron/projects/<name>/ containing:
- config.yml         — repo, backend, model preferences
- sprints.json       — history of all sprints (KPIs, retros, agents)
- profiles/          — agentspec agent profiles (signed)
- agents/            — .agent manifests (per-task)
- agent_versions.json — legacy agent version store (compatibility)
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

CALORON_HOME = Path(os.environ.get("CALORON_HOME", str(Path.home() / ".caloron")))
PROJECTS_DIR = CALORON_HOME / "projects"
GLOBAL_CONFIG = CALORON_HOME / "config.yml"
ACTIVE_PROJECT_FILE = CALORON_HOME / "active"


@dataclass
class Project:
    """A caloron project — one repo, one history."""

    name: str
    path: Path
    repo: str = ""                       # gitea://host/org/repo or github://...
    backend: str = "direct"              # direct | noether
    framework: str = "claude-code"
    work_dir: str = ""                   # where sprints actually run

    @property
    def config_path(self) -> Path:
        return self.path / "config.yml"

    @property
    def sprints_path(self) -> Path:
        return self.path / "sprints.json"

    @property
    def profiles_dir(self) -> Path:
        return self.path / "profiles"

    @property
    def agents_dir(self) -> Path:
        return self.path / "agents"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "repo": self.repo,
            "backend": self.backend,
            "framework": self.framework,
            "work_dir": self.work_dir,
        }


class ProjectStore:
    """Manages all caloron projects."""

    def __init__(self) -> None:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Project]:
        """List all known projects."""
        projects: list[Project] = []
        for d in sorted(PROJECTS_DIR.iterdir()):
            if d.is_dir():
                p = self._load(d)
                if p:
                    projects.append(p)
        return projects

    def get(self, name: str) -> Optional[Project]:
        path = PROJECTS_DIR / name
        if not path.exists():
            return None
        return self._load(path)

    def _load(self, path: Path) -> Optional[Project]:
        config = path / "config.yml"
        if not config.exists():
            # Default project from directory name only
            return Project(name=path.name, path=path)
        data = yaml.safe_load(config.read_text()) or {}
        return Project(
            name=path.name,
            path=path,
            repo=data.get("repo", ""),
            backend=data.get("backend", "direct"),
            framework=data.get("framework", "claude-code"),
            work_dir=data.get("work_dir", ""),
        )

    def create(
        self,
        name: str,
        repo: str = "",
        backend: str = "direct",
        framework: str = "claude-code",
        work_dir: str = "",
    ) -> Project:
        """Create a new project."""
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"Invalid project name: {name!r}")

        path = PROJECTS_DIR / name
        if path.exists():
            raise FileExistsError(f"Project already exists: {name}")

        path.mkdir(parents=True)
        (path / "profiles").mkdir()
        (path / "agents").mkdir()

        # Default work_dir under the project
        if not work_dir:
            work_dir = str(path / "workspace")
            Path(work_dir).mkdir(parents=True, exist_ok=True)

        project = Project(
            name=name,
            path=path,
            repo=repo,
            backend=backend,
            framework=framework,
            work_dir=work_dir,
        )

        config_data = {
            "name": name,
            "repo": repo,
            "backend": backend,
            "framework": framework,
            "work_dir": work_dir,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        project.config_path.write_text(yaml.dump(config_data, sort_keys=False))

        # Initialize empty sprints history
        project.sprints_path.write_text(json.dumps({"sprints": []}, indent=2))

        # Set as active if it's the first one
        if not ACTIVE_PROJECT_FILE.exists():
            self.set_active(name)

        return project

    def delete(self, name: str) -> bool:
        path = PROJECTS_DIR / name
        if not path.exists():
            return False
        shutil.rmtree(path)
        # Clear active if this was the active one
        if self.get_active() == name:
            ACTIVE_PROJECT_FILE.unlink(missing_ok=True)
        return True

    def set_active(self, name: str) -> None:
        if not (PROJECTS_DIR / name).exists():
            raise FileNotFoundError(f"Project not found: {name}")
        ACTIVE_PROJECT_FILE.write_text(name)

    def get_active(self) -> Optional[str]:
        if ACTIVE_PROJECT_FILE.exists():
            return ACTIVE_PROJECT_FILE.read_text().strip()
        return None

    def active(self) -> Optional[Project]:
        name = self.get_active()
        if not name:
            return None
        return self.get(name)

    def add_sprint(self, project: Project, sprint_data: dict[str, Any]) -> int:
        """Append a sprint result to the project's history."""
        history = json.loads(project.sprints_path.read_text())
        sprint_data["sprint_id"] = len(history["sprints"]) + 1
        sprint_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        history["sprints"].append(sprint_data)
        project.sprints_path.write_text(json.dumps(history, indent=2))
        return sprint_data["sprint_id"]

    def get_sprints(self, project: Project) -> list[dict[str, Any]]:
        if not project.sprints_path.exists():
            return []
        return json.loads(project.sprints_path.read_text()).get("sprints", [])

    def get_sprint(self, project: Project, sprint_id: int) -> Optional[dict[str, Any]]:
        for s in self.get_sprints(project):
            if s.get("sprint_id") == sprint_id:
                return s
        return None
