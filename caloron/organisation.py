"""Organisation conventions — a house style every sprint's agents must follow.

Lives at ``$CALORON_HOME/organisation.yml`` (typically ``~/.caloron/``) so one
file applies to every project a team runs through caloron. Overridden per
project by ``<project>/caloron.yml`` at repo root when present.

The schema is intentionally narrow for the MVP:

    organisation: "Alpibru Labs"
    package_naming:
        style: kebab-case    # or snake_case, PascalCase
        prefix: "alpibru-"   # optional
    imports:
        namespace: "alpibru" # optional root package name
        style: absolute      # or relative
    repository_layout:
        tests: tests/        # or src-adjacent, etc. — free-form string
        src: src/
    license:
        header: |
            Copyright (c) Alpibru Labs. Licensed under EUPL-1.2.
    dependencies:
        disallow: [GPL, AGPL]  # surfaces as a rule in the agent prompt
    commit_message:
        format: "<type>(<scope>): <summary>"
    branch_naming:
        format: "<type>/<ticket>-<slug>"

Every field is optional. The loader tolerates missing sections and never
raises — an invalid file becomes an empty set of rules plus a warning,
so a broken config never takes a sprint with it.

What this module does NOT do:
- Enforce conventions at tool level (ruff / pre-commit / CI); that's a
  separate layer (see roadmap).
- Validate package names / paths against real PEP 503 / cargo rules;
  only shape validation is done here.
- Merge with agentspec profile state — conventions are org-wide, not
  per-agent.

Rules get rendered into a markdown block the orchestrator appends to
every agent prompt + the PO context. That's the whole enforcement
mechanism today: "the agent saw the rule in its context."
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CALORON_HOME = Path(os.environ.get("CALORON_HOME", str(Path.home() / ".caloron")))
GLOBAL_CONVENTIONS_FILE = CALORON_HOME / "organisation.yml"
PROJECT_CONVENTIONS_FILENAME = "caloron.yml"


@dataclass
class Conventions:
    """Loaded + validated organisation conventions.

    Every field is optional; absent fields render to nothing in the prompt.
    ``source`` records where the conventions were loaded from, for diagnostics.
    """

    organisation: str = ""
    package_naming: dict[str, Any] = field(default_factory=dict)
    imports: dict[str, Any] = field(default_factory=dict)
    repository_layout: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)
    commit_message: dict[str, Any] = field(default_factory=dict)
    branch_naming: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    warnings: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True if no convention section carries content.

        Used to decide whether to render the convention block at all —
        avoids emitting an empty `## Organisation Conventions` header when
        the user hasn't configured anything.
        """
        for attr in (
            "organisation",
            "package_naming",
            "imports",
            "repository_layout",
            "license",
            "dependencies",
            "commit_message",
            "branch_naming",
            "extra",
        ):
            val = getattr(self, attr)
            if val:
                return False
        return True

    def render_prompt_block(self) -> str:
        """Render the conventions as a markdown section for agent prompts.

        Returns an empty string when there are no conventions — the caller
        can append unconditionally without littering prompts with empty
        headers. Keeps the format stable so sprint-to-sprint prompt
        compression actually compresses (identical text → cache hit).
        """
        if self.is_empty():
            return ""

        lines = ["## Organisation Conventions"]
        if self.organisation:
            lines.append(f"(Organisation: {self.organisation})")
        lines.append("")

        if self.package_naming:
            lines.append("### Package & module naming")
            style = self.package_naming.get("style")
            prefix = self.package_naming.get("prefix")
            if style:
                lines.append(f"- Package names use **{style}**.")
            if prefix:
                lines.append(f"- All package names must start with `{prefix}`.")
            lines.append("")

        if self.imports:
            lines.append("### Imports")
            ns = self.imports.get("namespace")
            style = self.imports.get("style")
            if ns:
                lines.append(f"- Root namespace is `{ns}` (e.g. `from {ns}.module import …`).")
            if style:
                lines.append(f"- Use **{style}** imports, not the other form.")
            lines.append("")

        if self.repository_layout:
            lines.append("### Repository layout")
            for key, value in self.repository_layout.items():
                lines.append(f"- `{key}` → `{value}`")
            lines.append("")

        if self.license:
            header = self.license.get("header")
            if header:
                lines.append("### License header (top of every new source file)")
                lines.append("```")
                lines.append(header.rstrip())
                lines.append("```")
                lines.append("")

        if self.dependencies:
            disallow = self.dependencies.get("disallow") or []
            if disallow:
                lines.append("### Dependencies")
                lines.append(
                    "- Disallowed licenses/packages: "
                    + ", ".join(f"`{d}`" for d in disallow)
                )
                lines.append("")

        if self.commit_message:
            fmt = self.commit_message.get("format")
            if fmt:
                lines.append("### Commit messages")
                lines.append(f"- Format: `{fmt}`")
                lines.append("")

        if self.branch_naming:
            fmt = self.branch_naming.get("format")
            if fmt:
                lines.append("### Branch naming")
                lines.append(f"- Format: `{fmt}`")
                lines.append("")

        if self.extra:
            lines.append("### Other")
            for key, value in self.extra.items():
                lines.append(f"- **{key}**: {value}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


# ── Loader ──────────────────────────────────────────────────────────────────


_KNOWN_SECTIONS = {
    "organisation",
    "package_naming",
    "imports",
    "repository_layout",
    "license",
    "dependencies",
    "commit_message",
    "branch_naming",
}


def load_conventions(
    *,
    project_dir: str | os.PathLike | None = None,
    global_file: Path | None = None,
) -> Conventions:
    """Load conventions.

    Precedence: project-level overrides global. Missing files are silent
    (return empty conventions). Malformed files produce a Conventions
    with ``warnings`` set but no exception — sprints never crash on a
    bad org config.
    """
    global_path = global_file or GLOBAL_CONVENTIONS_FILE
    global_data = _read_yaml(global_path)
    global_warns = global_data.pop("__warnings__", [])

    project_data: dict[str, Any] = {}
    project_warns: list[str] = []
    source = str(global_path) if global_path.exists() else ""
    if project_dir:
        project_path = Path(project_dir) / PROJECT_CONVENTIONS_FILENAME
        if project_path.exists():
            project_data = _read_yaml(project_path)
            project_warns = project_data.pop("__warnings__", [])
            source = (
                f"{source}; {project_path}" if source else str(project_path)
            )

    merged = _deep_merge(global_data, project_data)
    extra = {k: v for k, v in merged.items() if k not in _KNOWN_SECTIONS}
    return Conventions(
        organisation=str(merged.get("organisation", "")),
        package_naming=dict(merged.get("package_naming") or {}),
        imports=dict(merged.get("imports") or {}),
        repository_layout=dict(merged.get("repository_layout") or {}),
        license=dict(merged.get("license") or {}),
        dependencies=dict(merged.get("dependencies") or {}),
        commit_message=dict(merged.get("commit_message") or {}),
        branch_naming=dict(merged.get("branch_naming") or {}),
        extra=extra,
        source=source,
        warnings=global_warns + project_warns,
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a dict; never raises.

    Returns ``{}`` for missing/empty files and ``{"__warnings__": [...]}``
    when parsing fails so the caller can surface the issue without
    blowing up the sprint.
    """
    if not path.exists():
        return {}
    try:
        text = path.read_text()
    except OSError as exc:
        return {"__warnings__": [f"could not read {path}: {exc}"]}
    if not text.strip():
        return {}
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {"__warnings__": [f"YAML error in {path}: {exc}"]}
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        return {
            "__warnings__": [
                f"{path}: expected a mapping at the top level, got "
                f"{type(parsed).__name__}"
            ]
        }
    return parsed


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Right-wins recursive merge for dicts; everything else is replaced."""
    if not overlay:
        return dict(base)
    out: dict[str, Any] = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out
