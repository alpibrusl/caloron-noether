"""Caloron CLI — ACLI-compliant entry point.

Commands:
- init        Create a new project
- sprint      Run an autonomous sprint
- status      Show current sprint state
- history     List past sprints
- show        Detailed retro for a specific sprint
- metrics     Aggregated KPIs across the project
- agents      Show agent profiles in this project
- projects    list / switch / delete projects
- config      get / set configuration values
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer
from acli import (
    ACLIApp,
    ConflictError,
    InvalidArgsError,
    NotFoundError,
    OutputFormat,
    PreconditionError,
    acli_command,
    emit,
    success_envelope,
)

from caloron import __version__
from caloron.metrics.collector import MetricsCollector
from caloron.project.store import Project, ProjectStore

app = ACLIApp(
    name="caloron",
    version=__version__,
    help="Autonomous AI sprint orchestration",
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _run_plan_graph(graph_path: Path, goal: str) -> list[dict]:
    """Execute a Noether composition graph and extract its ``tasks`` output.

    The graph must emit ``{tasks: [...]}`` — that's the contract for use
    with ``caloron sprint --graph``. See ``compositions/sprint_plan.json``
    for the reference example.
    """
    if not graph_path.is_file():
        raise NotFoundError(f"Graph file not found: {graph_path}")
    if not shutil.which("noether"):
        raise PreconditionError(
            "`noether` CLI not found on $PATH",
            hint="Install Noether v0.3.0+ (cargo install noether-cli) or drop --graph",
        )

    # Noether's nix-sandboxed stages can't reach the user's subscription
    # CLI auth state, so subprocess-based LLM providers stall and get
    # killed by the 30s stage timeout. Skip the CLI path by default when
    # we invoke the graph from here — API keys and the template fallback
    # still work. Users who want to force a specific provider can set
    # CALORON_LLM_PROVIDER themselves.
    sub_env = os.environ.copy()
    sub_env.setdefault("CALORON_LLM_SKIP_CLI", "1")

    input_payload = json.dumps({"goal": goal, "constraints": ""})
    try:
        proc = subprocess.run(
            ["noether", "run", str(graph_path), "--input", input_payload],
            capture_output=True,
            text=True,
            timeout=300,
            env=sub_env,
        )
    except subprocess.TimeoutExpired as e:
        raise PreconditionError(f"noether run timed out after 300s: {e}") from e

    if proc.returncode != 0:
        raise PreconditionError(
            f"noether run failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout or '').strip()[:400]}"
        )

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise PreconditionError(f"noether output was not JSON: {e}") from e

    # Accept either an ACLI envelope ({ok, data, ...}) or the raw output.
    data = envelope.get("data", envelope) if isinstance(envelope, dict) else {}
    # Graph output is sometimes nested one level (e.g. {"output": {...}}).
    if isinstance(data, dict) and "tasks" not in data and "output" in data:
        data = data["output"] or {}
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise PreconditionError(
            "Graph did not emit a non-empty 'tasks' list in its output",
            hint="The final stage must output {tasks: [...]}. "
                 "See compositions/sprint_plan.json for a working example.",
        )
    return tasks


def _resolve_sandbox() -> str:
    """Pick a sandbox script: user override → bwrap on Linux → passthrough."""
    override = os.environ.get("SANDBOX")
    if override:
        return override

    import caloron as _pkg
    scripts_dir = Path(_pkg.__file__).parent / "_scripts"
    # Fallback: repo layout (editable install or source checkout)
    if not scripts_dir.exists():
        scripts_dir = Path(__file__).parent.parent.parent / "scripts"

    bwrap_sandbox = scripts_dir / "sandbox-agent.sh"
    passthrough = scripts_dir / "sandbox-passthrough.sh"

    if platform.system() == "Linux" and shutil.which("bwrap") and bwrap_sandbox.exists():
        return str(bwrap_sandbox)
    return str(passthrough)


def _get_active_or_fail(store: ProjectStore) -> Project:
    project = store.active()
    if not project:
        raise PreconditionError(
            "No active project. Run `caloron init <name>` or `caloron projects switch <name>`",
            hint="See `caloron projects list` for existing projects",
        )
    return project


# ── init ───────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("Initialize a new project", "caloron init my-project"),
        ("With a Gitea repo", "caloron init my-project --repo gitea://localhost:3000/myorg/myrepo"),
        ("With Noether backend", "caloron init my-project --backend noether"),
    ],
    idempotent=False,
    see_also=["sprint", "projects"],
)
def init(
    name: str = typer.Argument(help="Project name. type:string"),
    repo: str = typer.Option("", "--repo", "-r", help="Git repository URL. type:string"),
    backend: str = typer.Option("direct", "--backend", "-b", help="Sprint backend: direct or noether. type:enum[direct|noether]"),
    framework: str = typer.Option("claude-code", "--framework", "-f", help="Default agent framework. type:string"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Initialize a new caloron project."""
    start = time.time()
    store = ProjectStore()

    try:
        project = store.create(name=name, repo=repo, backend=backend, framework=framework)
    except FileExistsError as e:
        raise ConflictError(
            str(e), hint=f"Use a different name or run `caloron projects delete {name}`"
        ) from e
    except ValueError as e:
        raise InvalidArgsError(str(e)) from e

    data = {
        "name": project.name,
        "path": str(project.path),
        "repo": project.repo,
        "backend": project.backend,
        "framework": project.framework,
        "active": True,
    }

    if output == OutputFormat.json:
        emit(success_envelope("init", data, version=__version__, start_time=start), output)
    else:
        sys.stdout.write(f"Created project: {name}\n")
        sys.stdout.write(f"  Path:      {project.path}\n")
        sys.stdout.write(f"  Backend:   {backend}\n")
        sys.stdout.write(f"  Framework: {framework}\n")
        if repo:
            sys.stdout.write(f"  Repo:      {repo}\n")
        sys.stdout.write("\nNow run: caloron sprint \"<your goal>\"\n")


# ── sprint ─────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("Run a sprint", "caloron sprint \"build a hotel rate anomaly detector\""),
        ("Override timeout", "caloron sprint \"...\" --timeout 600"),
        ("In specific project", "caloron sprint \"...\" --project my-other-project"),
    ],
    idempotent=False,
    see_also=["status", "history", "show"],
)
def sprint(
    goal: str = typer.Argument(help="Sprint goal description. type:string"),
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Per-agent timeout in seconds. type:number"),
    graph: str = typer.Option(
        "",
        "--graph",
        "-g",
        help="Path to a Noether composition graph. If set, its {tasks} output replaces the built-in PO step. type:path",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Print PO prompt and other diagnostic output to stderr before execution. type:bool",
    ),
    po_timeout: str = typer.Option(
        "300",
        "--po-timeout",
        help="PO agent subprocess timeout in seconds, or 'auto' to scale with sprint count (300 + 60s per prior sprint, capped at 900s). Defaults to 300. type:string",
    ),
    skip_gitea_check: bool = typer.Option(
        False,
        "--skip-gitea-check",
        help="Skip the Gitea preflight check. Sprints still run but any git/issue/PR calls will be silent no-ops. type:bool",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Run an autonomous sprint to achieve the given goal."""
    start = time.time()
    store = ProjectStore()

    if project_name:
        project = store.get(project_name)
        if not project:
            raise NotFoundError(f"Project not found: {project_name}")
    else:
        project = _get_active_or_fail(store)

    # Find the orchestrator (legacy script)
    orchestrator_path = Path(__file__).parent.parent.parent / "orchestrator" / "orchestrator.py"
    if not orchestrator_path.exists():
        raise PreconditionError(
            f"Orchestrator script not found: {orchestrator_path}",
            hint="Make sure caloron-noether package is installed correctly",
        )

    # Non-claude frameworks are wired up with agentic flags (see FRAMEWORKS
    # in orchestrator.py), but integration is less battle-tested than
    # claude-code. Surface a single-line note so failures are easier to
    # attribute.
    if project.framework and project.framework != "claude-code":
        sys.stderr.write(
            f"Note: framework '{project.framework}' uses agentic/auto-approval mode. "
            "If you see 'no JSON' or empty diffs, confirm the CLI is authenticated "
            "and on $PATH (see https://github.com/alpibrusl/caloron-noether/issues/3).\n"
        )

    # Build environment for the orchestrator
    env = os.environ.copy()
    env["WORK"] = project.work_dir or str(project.path / "workspace")
    env["CALORON_BACKEND"] = project.backend
    env["CALORON_FRAMEWORK"] = project.framework or "claude-code"
    env["AGENT_TIMEOUT"] = str(timeout)

    # Load organisation conventions and pass the rendered block through
    # to the orchestrator as an env var. Project-level overrides come
    # from <project-workdir>/caloron.yml when present. Empty block
    # short-circuits — no env var set, orchestrator appends nothing.
    from caloron.organisation import load_conventions

    project_workdir = project.work_dir or str(project.path / "workspace")
    conventions = load_conventions(project_dir=project_workdir)
    if conventions.warnings:
        for w in conventions.warnings:
            sys.stderr.write(f"⚠️  org conventions: {w}\n")
    rendered_conventions = conventions.render_prompt_block()
    if rendered_conventions:
        env["CALORON_CONVENTIONS"] = rendered_conventions
        sys.stderr.write(
            f"✓ Loaded {len(rendered_conventions)} chars of org conventions "
            f"from {conventions.source}\n"
        )

    # Pass through verbatim — 'auto' is a valid value (orchestrator scales
    # with sprint count); numeric strings work as before.
    po_timeout_str = str(po_timeout).strip().lower()
    if po_timeout_str != "auto":
        try:
            int(po_timeout_str)
        except ValueError as e:
            raise InvalidArgsError(
                f"--po-timeout must be an integer or 'auto', got {po_timeout!r}"
            ) from e
    env["PO_TIMEOUT"] = po_timeout_str
    env["SANDBOX"] = _resolve_sandbox()
    if debug:
        env["CALORON_DEBUG"] = "1"
    if skip_gitea_check:
        env["CALORON_SKIP_GITEA_CHECK"] = "1"

    # If the user supplied a plan graph, run it now and hand the resulting
    # tasks to the orchestrator via a precomputed DAG file. The orchestrator
    # honours CALORON_PRECOMPUTED_TASKS by skipping its built-in PO step.
    if graph:
        tasks = _run_plan_graph(Path(graph), goal)
        Path(env["WORK"]).mkdir(parents=True, exist_ok=True)
        tasks_file = Path(env["WORK"]) / "precomputed_tasks.json"
        tasks_file.write_text(json.dumps(tasks, indent=2))
        env["CALORON_PRECOMPUTED_TASKS"] = str(tasks_file)
        sys.stderr.write(
            f"Using graph '{graph}' — {len(tasks)} precomputed task(s) "
            "replace the built-in PO step.\n"
        )

    if output == OutputFormat.json:
        # In JSON mode, capture and parse the orchestrator output
        result = subprocess.run(
            [sys.executable, str(orchestrator_path), goal],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout * 20,
        )
        sprint_data = _parse_orchestrator_output(result.stdout)
        sprint_id = store.add_sprint(project, {
            **sprint_data,
            "goal": goal,
            "exit_code": result.returncode,
            "duration_s": int(time.time() - start),
        })
        emit(success_envelope("sprint", {
            "sprint_id": sprint_id,
            "project": project.name,
            "duration_s": int(time.time() - start),
            "exit_code": result.returncode,
            **sprint_data,
        }, version=__version__, start_time=start), output)
    else:
        # In text mode, stream live to stdout
        sys.stdout.write(f"Project: {project.name}\n")
        sys.stdout.write(f"Goal:    {goal}\n\n")
        result = subprocess.run(
            [sys.executable, str(orchestrator_path), goal],
            env=env,
            timeout=timeout * 20,
        )
        # Parse the saved feedback file if it exists for accurate metrics
        sprint_data = _collect_sprint_results(project)
        sprint_id = store.add_sprint(project, {
            **sprint_data,
            "goal": goal,
            "exit_code": result.returncode,
            "duration_s": int(time.time() - start),
        })
        sys.stdout.write(f"\nSprint #{sprint_id} recorded in {project.name}\n")


def _parse_orchestrator_output(text: str) -> dict:
    """Best-effort extraction of metrics from orchestrator stdout."""
    import re

    data = {
        "completed_tasks": 0,
        "failed_tasks": 0,
        "total_tasks": 0,
        "avg_clarity": 0.0,
        "supervisor_events": 0,
        "blockers": [],
        "tools_used": [],
    }

    # Match patterns from the orchestrator's retro output
    for pat, key, conv in [
        (r"Tasks completed:\s+(\d+)/(\d+)", None, None),
        (r"Failed/crashed:\s+(\d+)", "failed_tasks", int),
        (r"Avg clarity:\s+([\d.]+)/10", "avg_clarity", float),
        (r"Supervisor events:\s+(\d+)", "supervisor_events", int),
    ]:
        m = re.search(pat, text)
        if m:
            if key:
                data[key] = conv(m.group(1))
            else:  # special: tasks completed/total
                data["completed_tasks"] = int(m.group(1))
                data["total_tasks"] = int(m.group(2))

    return data


def _collect_sprint_results(project: Project) -> dict:
    """Read sprint feedback from the WORK directory after orchestrator runs."""
    work = Path(project.work_dir or project.path / "workspace")
    learnings_file = work / "learnings.json"
    if not learnings_file.exists():
        return {}

    try:
        learnings = json.loads(learnings_file.read_text())
        if learnings.get("sprints"):
            last = learnings["sprints"][-1]
            return {
                "total_tasks": last.get("total", 0),
                "completed_tasks": last.get("completed", 0),
                "failed_tasks": last.get("failed", 0),
                "avg_clarity": last.get("avg_clarity", 0),
                "supervisor_events": last.get("supervisor_events", 0),
                "sprint_time_s": last.get("sprint_time_s", 0),
                "blockers": last.get("blockers", []),
            }
    except Exception:
        pass
    return {}


# ── status ─────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("Show current project status", "caloron status"),
        ("JSON output", "caloron status --output json"),
    ],
    idempotent=True,
    see_also=["history", "metrics"],
)
def status(
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Show current project status: active project, last sprint, basic stats."""
    start = time.time()
    store = ProjectStore()
    active = store.active()

    if not active:
        if output == OutputFormat.json:
            emit(success_envelope("status", {"active": None, "projects": len(store.list())},
                                   version=__version__, start_time=start), output)
        else:
            sys.stdout.write("No active project.\n")
            projects = store.list()
            if projects:
                sys.stdout.write(f"({len(projects)} project(s) exist — see `caloron projects list`)\n")
            else:
                sys.stdout.write("Run `caloron init <name>` to create one.\n")
        return

    sprints = store.get_sprints(active)
    last = sprints[-1] if sprints else None

    data = {
        "project": active.name,
        "path": str(active.path),
        "repo": active.repo,
        "backend": active.backend,
        "framework": active.framework,
        "total_sprints": len(sprints),
        "last_sprint": last,
    }

    if output == OutputFormat.json:
        emit(success_envelope("status", data, version=__version__, start_time=start), output)
    else:
        sys.stdout.write(f"Active project: {active.name}\n")
        sys.stdout.write(f"  Backend:    {active.backend}\n")
        sys.stdout.write(f"  Framework:  {active.framework}\n")
        if active.repo:
            sys.stdout.write(f"  Repo:       {active.repo}\n")
        sys.stdout.write(f"  Sprints:    {len(sprints)}\n")
        if last:
            tasks = f"{last.get('completed_tasks', 0)}/{last.get('total_tasks', 0)}"
            sys.stdout.write(f"  Last:       sprint #{last.get('sprint_id')} — {tasks} tasks "
                             f"(clarity {last.get('avg_clarity', 0):.1f}/10)\n")
        else:
            sys.stdout.write("  Last:       no sprints yet — run `caloron sprint \"<goal>\"`\n")


# ── history ────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("List sprints in current project", "caloron history"),
        ("Last 5 sprints", "caloron history --limit 5"),
        ("In specific project", "caloron history --project my-other-project"),
    ],
    idempotent=True,
    see_also=["show", "metrics"],
)
def history(
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of sprints to show. type:number"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """List past sprints in a project."""
    start = time.time()
    store = ProjectStore()
    project = store.get(project_name) if project_name else _get_active_or_fail(store)
    if not project:
        raise NotFoundError(f"Project not found: {project_name}")

    sprints = store.get_sprints(project)[-limit:]

    if output == OutputFormat.json:
        emit(success_envelope("history", {
            "project": project.name,
            "total": len(store.get_sprints(project)),
            "sprints": sprints,
        }, version=__version__, start_time=start), output)
    elif output == OutputFormat.table:
        sys.stdout.write(f"{'#':>4}  {'Tasks':>8}  {'Clarity':>8}  {'Time':>6}  Goal\n")
        sys.stdout.write("-" * 80 + "\n")
        for s in sprints:
            sid = s.get("sprint_id", "?")
            tasks = f"{s.get('completed_tasks', 0)}/{s.get('total_tasks', 0)}"
            clarity = f"{s.get('avg_clarity', 0):.1f}/10"
            time_s = f"{s.get('duration_s', s.get('sprint_time_s', 0))}s"
            goal = (s.get("goal", "?") or "?")[:60]
            sys.stdout.write(f"{sid:>4}  {tasks:>8}  {clarity:>8}  {time_s:>6}  {goal}\n")
    else:
        if not sprints:
            sys.stdout.write(f"No sprints in {project.name} yet.\n")
        else:
            sys.stdout.write(f"Sprints in {project.name} ({len(sprints)} shown):\n\n")
            for s in sprints:
                sid = s.get("sprint_id", "?")
                tasks = f"{s.get('completed_tasks', 0)}/{s.get('total_tasks', 0)}"
                sys.stdout.write(f"  #{sid}  {tasks} tasks, clarity {s.get('avg_clarity', 0):.1f}/10  "
                                 f"({s.get('duration_s', s.get('sprint_time_s', 0))}s)\n")
                sys.stdout.write(f"      {(s.get('goal') or '')[:80]}\n")


# ── show ───────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("Show sprint #5 details", "caloron show 5"),
        ("In specific project", "caloron show 5 --project my-project"),
    ],
    idempotent=True,
    see_also=["history", "metrics"],
)
def show(
    sprint_id: int = typer.Argument(help="Sprint ID. type:number"),
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Show full retro details for a specific sprint."""
    start = time.time()
    store = ProjectStore()
    project = store.get(project_name) if project_name else _get_active_or_fail(store)
    if not project:
        raise NotFoundError(f"Project not found: {project_name}")

    sprint = store.get_sprint(project, sprint_id)
    if not sprint:
        raise NotFoundError(f"Sprint #{sprint_id} not found in {project.name}")

    if output == OutputFormat.json:
        emit(success_envelope("show", sprint, version=__version__, start_time=start), output)
    else:
        sys.stdout.write(f"Sprint #{sprint_id} — {project.name}\n")
        sys.stdout.write(f"  Goal:        {sprint.get('goal', '?')}\n")
        sys.stdout.write(f"  Completed:   {sprint.get('completed_tasks', 0)}/{sprint.get('total_tasks', 0)}\n")
        sys.stdout.write(f"  Failed:      {sprint.get('failed_tasks', 0)}\n")
        sys.stdout.write(f"  Avg clarity: {sprint.get('avg_clarity', 0):.1f}/10\n")
        sys.stdout.write(f"  Sprint time: {sprint.get('duration_s', sprint.get('sprint_time_s', 0))}s\n")
        sys.stdout.write(f"  Supervisor:  {sprint.get('supervisor_events', 0)} events\n")
        sys.stdout.write(f"  Completed:   {sprint.get('completed_at', '?')}\n")

        blockers = sprint.get("blockers", [])
        if blockers:
            sys.stdout.write(f"\n  Blockers ({len(blockers)}):\n")
            for b in blockers[:10]:
                sys.stdout.write(f"    - {b}\n")


# ── metrics ────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("Show project metrics", "caloron metrics"),
        ("In specific project", "caloron metrics --project my-other-project"),
        ("JSON for dashboards", "caloron metrics --output json"),
    ],
    idempotent=True,
    see_also=["history", "show"],
)
def metrics(
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Show aggregated KPIs across all sprints in a project."""
    start = time.time()
    store = ProjectStore()
    project = store.get(project_name) if project_name else _get_active_or_fail(store)
    if not project:
        raise NotFoundError(f"Project not found: {project_name}")

    collector = MetricsCollector(store)
    m = collector.collect(project)

    data = {
        "project": project.name,
        "total_sprints": m.total_sprints,
        "total_tasks": m.total_tasks,
        "completed_tasks": m.total_completed,
        "failed_tasks": m.total_failed,
        "completion_rate": m.completion_rate,
        "avg_clarity": m.avg_clarity,
        "avg_sprint_time_s": m.avg_sprint_time_s,
        "supervisor_events": m.total_supervisor_events,
        "tests_passing": m.total_tests_passing,
        "top_blockers": m.most_common_blockers,
        "top_tools": m.tools_used,
    }

    if output == OutputFormat.json:
        emit(success_envelope("metrics", data, version=__version__, start_time=start), output)
    else:
        if m.total_sprints == 0:
            sys.stdout.write(f"No sprints yet in {project.name}.\n")
            return
        sys.stdout.write(f"Metrics for {project.name}\n")
        sys.stdout.write(f"  Total sprints:       {m.total_sprints}\n")
        sys.stdout.write(f"  Total tasks:         {m.total_tasks}\n")
        sys.stdout.write(f"  Completed:           {m.total_completed} ({m.completion_rate:.0%})\n")
        sys.stdout.write(f"  Failed:              {m.total_failed}\n")
        sys.stdout.write(f"  Avg clarity:         {m.avg_clarity:.2f}/10\n")
        sys.stdout.write(f"  Avg sprint time:     {m.avg_sprint_time_s:.0f}s\n")
        sys.stdout.write(f"  Supervisor events:   {m.total_supervisor_events}\n")
        if m.most_common_blockers:
            sys.stdout.write("\n  Most common blockers:\n")
            for blocker, count in m.most_common_blockers:
                sys.stdout.write(f"    {count:>3}× {blocker}\n")
        if m.tools_used:
            sys.stdout.write("\n  Most used tools:\n")
            for tool, count in m.tools_used[:5]:
                sys.stdout.write(f"    {count:>3}× {tool}\n")


# ── agents ─────────────────────────────────────────────────────────────────


@app.command()
@acli_command(
    examples=[
        ("List agents in project", "caloron agents"),
        ("Show specific agent profile", "caloron agents impl"),
    ],
    idempotent=True,
    see_also=["metrics"],
)
def agents(
    agent_id: str = typer.Argument("", help="Agent ID (optional). type:string"),
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Show agent profiles in this project."""
    start = time.time()
    store = ProjectStore()
    project = store.get(project_name) if project_name else _get_active_or_fail(store)
    if not project:
        raise NotFoundError(f"Project not found: {project_name}")

    profiles_dir = project.profiles_dir
    profile_files = sorted(profiles_dir.glob("*.profile.json")) if profiles_dir.exists() else []

    if not profile_files:
        if output == OutputFormat.json:
            emit(success_envelope("agents", {"agents": []}, version=__version__, start_time=start), output)
        else:
            sys.stdout.write(f"No agent profiles in {project.name}.\n")
            sys.stdout.write("Profiles are created when agents complete sprints.\n")
        return

    summaries = []
    for pf in profile_files:
        try:
            data = json.loads(pf.read_text())
            summary = {
                "agent_id": data.get("agent_id", pf.stem.replace(".profile", "")),
                "version": data.get("manifest_version", "?"),
                "hash": data.get("agent_hash", "?"),
                "sprints": len(data.get("portfolio", [])),
                "memories": len(data.get("memories", [])),
                "skills": len(data.get("skills", [])),
                "top_skills": [s["skill"] for s in data.get("skills", [])[:3]],
            }
            summaries.append(summary)
        except Exception:
            continue

    # Filter to specific agent if requested
    if agent_id:
        summaries = [s for s in summaries if agent_id in s["agent_id"]]
        if not summaries:
            raise NotFoundError(f"Agent not found: {agent_id}")

    if output == OutputFormat.json:
        emit(success_envelope("agents", {"agents": summaries}, version=__version__, start_time=start), output)
    else:
        sys.stdout.write(f"Agents in {project.name} ({len(summaries)}):\n\n")
        for s in summaries:
            sys.stdout.write(f"  {s['agent_id']}  v{s['version']}  ({s['hash']})\n")
            sys.stdout.write(f"    Sprints: {s['sprints']}  Memories: {s['memories']}  Skills: {s['skills']}\n")
            if s["top_skills"]:
                sys.stdout.write(f"    Top skills: {', '.join(s['top_skills'])}\n")
            sys.stdout.write("\n")


# ── projects ───────────────────────────────────────────────────────────────

projects_app = typer.Typer(help="Manage caloron projects")
app.add_typer(projects_app, name="projects")


@projects_app.command("list")
def projects_list(
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """List all projects."""
    start = time.time()
    store = ProjectStore()
    projects = store.list()
    active = store.get_active()

    data = {
        "active": active,
        "projects": [{**p.to_dict(), "active": p.name == active} for p in projects],
    }
    if output == OutputFormat.json:
        emit(success_envelope("projects.list", data, version=__version__, start_time=start), output)
    elif not projects:
        sys.stdout.write("No projects yet. Run `caloron init <name>`.\n")
    else:
        sys.stdout.write(f"Projects ({len(projects)}):\n")
        for p in projects:
            marker = "* " if p.name == active else "  "
            sys.stdout.write(f"  {marker}{p.name}  ({p.backend})\n")


@projects_app.command("switch")
def projects_switch(
    name: str = typer.Argument(help="Project name. type:string"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Switch the active project."""
    start = time.time()
    store = ProjectStore()
    try:
        store.set_active(name)
    except FileNotFoundError as e:
        raise NotFoundError(str(e)) from e

    data = {"active": name}
    if output == OutputFormat.json:
        emit(success_envelope("projects.switch", data, version=__version__, start_time=start), output)
    else:
        sys.stdout.write(f"Active project: {name}\n")


@projects_app.command("delete")
def projects_delete(
    name: str = typer.Argument(help="Project name. type:string"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation. type:bool"),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Delete a project (and all its history)."""
    start = time.time()
    if not force:
        sys.stdout.write(f"This will delete project '{name}' and all its history. ")
        sys.stdout.write("Type the project name to confirm: ")
        confirmation = sys.stdin.readline().strip()
        if confirmation != name:
            sys.stdout.write("Cancelled.\n")
            raise SystemExit(1)

    store = ProjectStore()
    if not store.delete(name):
        raise NotFoundError(f"Project not found: {name}")

    data = {"deleted": name}
    if output == OutputFormat.json:
        emit(success_envelope("projects.delete", data, version=__version__, start_time=start), output)
    else:
        sys.stdout.write(f"Deleted project: {name}\n")


# ── config ─────────────────────────────────────────────────────────────────

config_app = typer.Typer(help="Get or set configuration values")
app.add_typer(config_app, name="config")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(help="Config key (e.g. backend, framework, repo). type:string"),
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
) -> None:
    """Get a config value from the active project."""
    store = ProjectStore()
    project = store.get(project_name) if project_name else _get_active_or_fail(store)
    if not project:
        raise NotFoundError(f"Project not found: {project_name}")

    value = getattr(project, key, None)
    if value is None:
        raise NotFoundError(f"Config key not found: {key}")
    sys.stdout.write(f"{value}\n")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key. type:string"),
    value: str = typer.Argument(help="New value. type:string"),
    project_name: str = typer.Option("", "--project", "-p", help="Project name (default: active). type:string"),
) -> None:
    """Set a config value in the active project."""
    import yaml
    store = ProjectStore()
    project = store.get(project_name) if project_name else _get_active_or_fail(store)
    if not project:
        raise NotFoundError(f"Project not found: {project_name}")

    valid_keys = {"repo", "backend", "framework", "work_dir"}
    if key not in valid_keys:
        raise InvalidArgsError(f"Unknown config key: {key}", hint=f"Valid keys: {', '.join(sorted(valid_keys))}")

    config_data = yaml.safe_load(project.config_path.read_text()) or {}
    config_data[key] = value
    project.config_path.write_text(yaml.dump(config_data, sort_keys=False))
    sys.stdout.write(f"Set {key} = {value} in {project.name}\n")


# ── org (organisation conventions) ─────────────────────────────────────────

org_app = typer.Typer(
    help="Manage organisation-wide conventions injected into every agent prompt"
)
app.add_typer(org_app, name="org")


_ORG_INIT_TEMPLATE = """# Organisation-wide conventions applied to every caloron sprint.
# See `caloron org show` to render the block agents will see, and
# `caloron org validate` to check shape. Every field is optional.

organisation: ""  # e.g. "Alpibru Labs"

package_naming:
  style: kebab-case   # or snake_case, PascalCase
  # prefix: "alpibru-"

imports:
  # namespace: "alpibru"
  style: absolute

repository_layout:
  src: src/
  tests: tests/

license:
  header: |
    Copyright (c) Your Company. All rights reserved.

dependencies:
  disallow: []   # e.g. [GPL, AGPL]

commit_message:
  format: "<type>(<scope>): <summary>"

branch_naming:
  format: "<type>/<ticket>-<slug>"
"""


@org_app.command("init")
def org_init() -> None:
    """Scaffold an organisation conventions file with sensible defaults.

    Writes to $CALORON_HOME/organisation.yml (default ~/.caloron/). If the
    file already exists, bails out rather than overwriting — use your
    editor or `caloron org set` to edit in place.
    """
    from caloron.organisation import GLOBAL_CONVENTIONS_FILE

    target = GLOBAL_CONVENTIONS_FILE
    if target.exists():
        raise ConflictError(
            f"{target} already exists",
            hint="Edit it directly, or delete and re-run `caloron org init`",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_ORG_INIT_TEMPLATE)
    sys.stdout.write(f"Created {target}\nEdit it to declare your conventions.\n")


@org_app.command("show")
def org_show(
    project: str = typer.Option(
        "", "--project", "-p", help="Merge in project-level overrides from <project>/caloron.yml. type:path"
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.text, "--output", help="Output format. type:enum[text|json|table]"
    ),
) -> None:
    """Render the conventions block agents will receive in every prompt."""
    from caloron.organisation import load_conventions

    start = time.time()
    conv = load_conventions(project_dir=project or None)
    rendered = conv.render_prompt_block()

    if output == OutputFormat.json:
        emit(
            success_envelope(
                "org.show",
                {
                    "source": conv.source,
                    "organisation": conv.organisation,
                    "is_empty": conv.is_empty(),
                    "rendered": rendered,
                    "warnings": conv.warnings,
                },
                version=__version__,
                start_time=start,
            ),
            output,
        )
        return

    if conv.warnings:
        for w in conv.warnings:
            sys.stderr.write(f"Warning: {w}\n")
    if conv.is_empty():
        sys.stdout.write(
            "(no conventions configured — run `caloron org init` to start)\n"
        )
        return
    sys.stdout.write(f"Source: {conv.source}\n\n")
    sys.stdout.write(rendered)


@org_app.command("validate")
def org_validate(
    project: str = typer.Option(
        "", "--project", "-p", help="Also validate <project>/caloron.yml. type:path"
    ),
) -> None:
    """Load the conventions file(s) and report any parse / shape issues."""
    from caloron.organisation import load_conventions

    conv = load_conventions(project_dir=project or None)
    if conv.warnings:
        for w in conv.warnings:
            sys.stdout.write(f"⚠️  {w}\n")
        raise SystemExit(1)
    if conv.is_empty():
        sys.stdout.write(
            "(no conventions configured — `caloron org init` to start)\n"
        )
        return
    sys.stdout.write(f"OK — loaded from {conv.source}\n")


# ── Entrypoint ─────────────────────────────────────────────────────────────


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
