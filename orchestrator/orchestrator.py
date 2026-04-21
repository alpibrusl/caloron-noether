#!/usr/bin/env python3
"""
Full autonomous sprint orchestrator — no mocks.

Handles: PO → issues → agents → PRs → reviews → merges → supervisor → retro.
Runs against local Gitea via Docker.
"""
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from agent_configurator import configure_agent, print_config_summary
from agent_versioning import AgentVersionStore, auto_evolve_agents, print_agent_history
from agentspec_bridge import (
    AGENTSPEC_AVAILABLE,
    auto_evolve_with_agentspec,
    configure_agent_from_spec,
    enrich_tasks_with_agentspec,
    print_agentspec_assignments,
    print_evolution_summary,
)
from hr_agent import print_assignments, run_hr_agent
from post_sprint_deploy import post_sprint_deploy, print_deploy_summary
from skill_store import SkillStore
from template_store import scaffold_project

# Bare-name imports match the convention of the surrounding sibling
# imports (`agent_configurator`, `hr_agent`, etc.). The orchestrator
# runs with its own directory on sys.path; a relative import breaks
# under that loader pattern.
from types_ import BlockedTaskDict, TaskDict  # noqa: I001
from validation import require_branch, require_id  # noqa: I001

# Profile integration (requires agentspec with profile module)
try:
    from agentspec.parser.manifest import AgentManifest as _AgentManifest
    from agentspec.profile.manager import ProfileManager
    PROFILES_AVAILABLE = True
except ImportError:
    PROFILES_AVAILABLE = False

# ── Config ──────────────────────────────────────────────────────────────────


def _require_gitea_token() -> str:
    """Read GITEA_TOKEN from the environment or fail loudly at import time.

    Previously defaulted to a hardcoded dev token when unset; that made
    deployments that forgot to set the env var use the baked-in token
    silently, which is the opposite of the desired failure mode. See
    issue #18.
    """
    token = os.environ.get("GITEA_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITEA_TOKEN environment variable is required. "
            "Create a Gitea API token (Settings → Applications → "
            "Generate New Token) and export it before running. "
            "See docs/deployment.md if you need guidance."
        )
    return token


GITEA_TOKEN = _require_gitea_token()
REPO = os.environ.get("REPO", "caloron/full-loop")
SANDBOX = os.environ.get("SANDBOX", str(Path(__file__).parent.parent.parent / "scripts" / "sandbox-agent.sh"))
WORK = os.environ.get("WORK", "/tmp/caloron-full-loop")
AGENT_TIMEOUT_S = int(os.environ.get("AGENT_TIMEOUT", "180"))  # 3 minutes
# PO agent's prompt grows with accumulated learnings, so it needs a
# bigger budget than per-task agents. Override with PO_TIMEOUT; use
# "auto" to scale with the number of prior sprints via auto_po_timeout().
_PO_TIMEOUT_ENV = os.environ.get("PO_TIMEOUT", "300").strip().lower()
PO_TIMEOUT_AUTO = _PO_TIMEOUT_ENV == "auto"
PO_TIMEOUT_S = 300 if PO_TIMEOUT_AUTO else int(_PO_TIMEOUT_ENV)
MAX_RETRIES = 2
LEARNINGS_FILE = os.path.join(os.environ.get("WORK", "/tmp/caloron-full-loop"), "learnings.json")

# Backend: "direct" (Claude CLI) or "noether" (via Noether stages)
BACKEND = os.environ.get("CALORON_BACKEND", "direct")

# Default agent framework — set by `caloron init --framework` via the CLI.
# Applies to the PO, HR, and reviewer agents; individual tasks may still
# override this in the PO-generated DAG.
FRAMEWORK = os.environ.get("CALORON_FRAMEWORK", "claude-code")

# Organisation conventions rendered into every prompt. Populated by
# ``caloron sprint`` from ``~/.caloron/organisation.yml`` + any
# project-level override. Empty string when no conventions configured.
CONVENTIONS = os.environ.get("CALORON_CONVENTIONS", "")


def _conventions_block(conventions: str) -> str:
    """Format the conventions string for inclusion at a prompt's tail.

    Returns an empty string when there are no conventions, so callers can
    unconditionally concatenate without emitting empty sections.
    """
    if not conventions.strip():
        return ""
    return "\n\n" + conventions.rstrip() + "\n"
NOETHER_STAGES_DIR = os.environ.get("NOETHER_STAGES_DIR",
    str(Path(__file__).parent.parent / "stages"))

# API keys — set any of these to use API mode instead of Claude Pro
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Framework registry ──────────────────────────────────────────────────────

FRAMEWORKS = {
    "claude-code": {
        "cmd": "claude",
        # --dangerously-skip-permissions is injected by build_agent_command
        # only when CALORON_ALLOW_DANGEROUS_CLAUDE is set; see claude_flags.py.
        "args": [],
        "prompt_flag": "-p",
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_key_flag": "--api-key",
    },
    "gemini-cli": {
        # -y/--yolo auto-approves tool calls (file write, shell), required
        # for non-interactive agentic runs. Without it, -p is one-shot Q&A.
        "cmd": "gemini",
        "args": ["-y"],
        "prompt_flag": "-p",
        "api_key_env": "GOOGLE_API_KEY",
        "api_key_flag": None,  # gemini-cli uses env var
    },
    "aider": {
        # --yes-always skips every confirmation prompt; aider edits files
        # natively in --message mode, so no extra tool flag is needed.
        "cmd": "aider",
        "args": ["--yes-always", "--no-auto-commits"],
        "prompt_flag": "--message",
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_key_flag": None,
    },
    "codex-cli": {
        # Current codex CLI uses `exec --full-auto <prompt>` (positional).
        # --full-auto is the preset for workspace-write sandbox + approval.
        "cmd": "codex",
        "args": ["exec", "--full-auto"],
        "prompt_flag": "",  # prompt is positional
        "api_key_env": "OPENAI_API_KEY",
        "api_key_flag": None,
    },
    "open-code": {
        # `opencode run <prompt>` ships with full tool access (build agent).
        "cmd": "opencode",
        "args": ["run"],
        "prompt_flag": "",  # opencode run takes message as positional arg
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_key_flag": None,
    },
    "cursor-cli": {
        # cursor-agent -p runs in print/headless mode with agent tools on.
        "cmd": "cursor-agent",
        "args": ["--output-format", "text"],
        "prompt_flag": "-p",
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_key_flag": None,
    },
    # ─────────────────────────────────────────────────────────────────────
    # Test-only: deterministic stub agent.
    #
    # Reads a canned response fixture from $CALORON_STUB_FIXTURE and
    # replays it on stdout, making end-to-end sprint loops runnable
    # without a live LLM CLI. The stub binary is a tiny Python script
    # shipped under ``scripts/stub_agent.py``. Used exclusively by
    # tests/test_sprint_chain_integration.py and any future full-loop
    # CI runs.
    #
    # Do NOT use this framework in production sprints — it has no
    # reasoning ability and will produce whatever the fixture dictates.
    "stub": {
        "cmd": "python3",
        "args": [str(Path(__file__).parent.parent / "scripts" / "stub_agent.py")],
        "prompt_flag": "--prompt",
        "api_key_env": "CALORON_STUB_FIXTURE",
        "api_key_flag": None,
    },
}


def build_agent_command(framework: str, prompt: str) -> list[str]:
    """Build the command list for a given framework and prompt."""
    from orchestrator.claude_flags import dangerous_flags

    fw = FRAMEWORKS.get(framework, FRAMEWORKS["claude-code"])

    cmd = [fw["cmd"]] + fw["args"]

    # Only claude-code has the dangerous-permissions flag; other runtimes
    # have their own autonomous-run switches already in fw["args"].
    if framework == "claude-code":
        cmd.extend(dangerous_flags())

    # Add API key if available (overrides Pro subscription login)
    api_key = os.environ.get(fw["api_key_env"], "")
    if api_key and fw.get("api_key_flag"):
        cmd.extend([fw["api_key_flag"], api_key])

    if fw["prompt_flag"]:
        cmd.extend([fw["prompt_flag"], prompt])
    else:
        # Prompt is a positional argument (codex exec, opencode run, …)
        cmd.append(prompt)
    return cmd


# ── Noether backend ────────────────────────────────────────────────────────

def run_noether_stage(stage_file: str, input_data: dict) -> dict:
    """Run a caloron-noether Python stage via stdin/stdout JSON."""
    stage_path = os.path.join(NOETHER_STAGES_DIR, stage_file)
    if not os.path.exists(stage_path):
        print(f"  WARNING: stage not found: {stage_path}")
        return {}
    result = subprocess.run(
        ["python3", stage_path],
        input=json.dumps(input_data),
        capture_output=True, text=True, timeout=30,
    )
    try:
        return json.loads(result.stdout)
    except Exception:
        if result.stderr:
            print(f"  Stage error: {result.stderr[:100]}")
        return {}


def noether_evaluate_dag(state: dict, events: list, stall_threshold_m: int = 20) -> dict:
    """Run DAG evaluation through the Noether stage."""
    return run_noether_stage("dag/evaluate.py", {
        "state": state,
        "events": events,
        "stall_threshold_m": stall_threshold_m,
    })


def noether_check_health(agents: dict, stall_threshold_m: int = 20) -> dict:
    """Run health check through the Noether stage."""
    return run_noether_stage("supervisor/check_health.py", {
        "agents": agents,
        "stall_threshold_m": stall_threshold_m,
    })


def noether_decide_intervention(results: list, interventions: dict) -> dict:
    """Run intervention decision through the Noether stage."""
    return run_noether_stage("supervisor/decide_intervention.py", {
        "results": results,
        "interventions": interventions,
    })


def noether_compute_kpis(state: dict, started_at: str, ended_at: str) -> dict:
    """Compute KPIs through the Noether stage."""
    return run_noether_stage("retro/compute_kpis.py", {
        "state": state,
        "started_at": started_at,
        "ended_at": ended_at,
    })


def noether_analyze_feedback(feedback_items: list, kpis: dict) -> dict:
    """Analyze feedback through the Noether stage."""
    return run_noether_stage("retro/analyze_feedback.py", {
        "feedback_items": feedback_items,
        "kpis": kpis,
    })


def noether_write_report(sprint_id: str, kpis: dict, feedback_items: list,
                          started_at: str, ended_at: str) -> dict:
    """Generate retro report through the Noether stage."""
    return run_noether_stage("retro/write_report.py", {
        "sprint_id": sprint_id,
        "kpis": kpis,
        "feedback_items": feedback_items,
        "started_at": started_at,
        "ended_at": ended_at,
    })


# ── Agent feedback parsing ───────────────────────────────────────────────────

def parse_agent_feedback(agent_output: str) -> dict:
    """Extract structured feedback from agent's stdout.

    Looks for CALORON_FEEDBACK_START ... JSON ... CALORON_FEEDBACK_END block.
    Returns parsed dict or defaults if not found.
    """
    defaults = {
        "task_clarity": 5,
        "blockers": [],
        "tools_used": ["claude-code"],
        "self_assessment": "completed",
        "notes": "",
    }

    if not agent_output:
        return defaults

    match = re.search(
        r"CALORON_FEEDBACK_START\s*(.*?)\s*CALORON_FEEDBACK_END",
        agent_output,
        re.DOTALL,
    )
    if not match:
        return defaults

    try:
        feedback = json.loads(match.group(1))
        # Validate and merge with defaults
        result = dict(defaults)
        for key in defaults:
            if key in feedback:
                result[key] = feedback[key]
        # Clamp clarity to 1-10
        result["task_clarity"] = max(1, min(10, int(result["task_clarity"])))
        # Validate assessment
        valid_assessments = ("completed", "partial", "blocked", "failed")
        if result["self_assessment"] not in valid_assessments:
            result["self_assessment"] = "completed"
        return result
    except (json.JSONDecodeError, ValueError, TypeError):
        return defaults


# ── Path filters ────────────────────────────────────────────────────────────


# Paths caloron writes itself (or that would pollute the PR) — keep the
# agent out of these while allowing broader scope than just src/ + tests/.
_CALORON_MANAGED_PREFIXES = (
    ".caloron/",
    ".noether/",
    ".git/",
)
_CALORON_MANAGED_FILES = {
    "CLAUDE.md",       # generated per-task by agent_configurator
    ".mcp.json",       # MCP registration
    ".cursorrules",
    "GEMINI.md",
    "AGENTS.md",
    ".aider.conf.yml",
}


def _is_caloron_managed(path: str) -> bool:
    """True if the path is one caloron writes itself and agents shouldn't."""
    if path in _CALORON_MANAGED_FILES:
        return True
    return any(path.startswith(p) for p in _CALORON_MANAGED_PREFIXES)


# ── Gitea API ───────────────────────────────────────────────────────────────

def gitea_available() -> tuple[bool, str]:
    """Preflight check: is the Gitea container running and reachable?

    Returns (ok, detail). ``ok=False`` means the orchestrator should abort
    or warn prominently — every gitea() call will silently return {} and
    the sprint will produce fake issue numbers, fake PRs, and no real
    version control, which is the worst possible failure mode for an
    autonomous tool.
    """
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=^gitea$", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, f"docker CLI not available: {e}"
    if r.returncode != 0 or "gitea" not in (r.stdout or ""):
        return False, "no running container named 'gitea'"
    try:
        ping = subprocess.run(
            ["docker", "exec", "gitea", "wget", "-qO-", "http://127.0.0.1:3000/api/v1/version"],
            capture_output=True, text=True, timeout=5,
        )
    except subprocess.TimeoutExpired:
        return False, "gitea container exists but /api/v1/version timed out"
    if ping.returncode != 0 or "version" not in (ping.stdout or ""):
        return False, "gitea container up but API not responding"
    return True, ping.stdout.strip()


def gitea(method: str, path: str, data: dict | None = None) -> dict:
    if method == "GET":
        r = subprocess.run(
            ["docker", "exec", "gitea", "wget", "-qO-",
             "--header", f"Authorization: token {GITEA_TOKEN}",
             f"http://127.0.0.1:3000{path}"],
            capture_output=True, text=True, timeout=15)
    else:
        r = subprocess.run(
            ["docker", "exec", "gitea", "wget", "-qO-",
             "--post-data", json.dumps(data),
             "--header", "Content-Type: application/json",
             "--header", f"Authorization: token {GITEA_TOKEN}",
             f"http://127.0.0.1:3000{path}"],
            capture_output=True, text=True, timeout=15)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def git_merge_branch(branch: str, message: str) -> bool:
    """Merge a branch into main via git inside the Gitea container.
    Temporarily disables the pre-receive hook (Gitea 1.22 merge API is broken for local setups).

    Validates ``branch`` and shell-escapes ``message`` before constructing
    the shell script — the script passes through ``docker exec ... sh -c``,
    so unescaped input becomes an injection path. See issue #19.
    """
    # Defense in depth: reject at the boundary rather than rely on
    # upstream callers to sanitise.
    require_branch("branch", branch)

    # Message is arbitrary human text (PR titles, commit messages) and
    # legitimately contains spaces, quotes, etc. — `shlex.quote` is the
    # correct escape hatch for shell-interpolated strings.
    quoted_message = shlex.quote(message)

    repo_path = f"/data/git/repositories/{REPO}.git"
    script = (
        f"chmod -x {repo_path}/hooks/pre-receive 2>/dev/null; "
        f"cd /tmp && rm -rf _merge && mkdir _merge && cd _merge && "
        f"git init -q && "
        f"git fetch {repo_path} main:main {branch}:{branch} 2>/dev/null && "
        f"git checkout main 2>/dev/null && "
        f"git merge {branch} -m {quoted_message} 2>/dev/null && "
        f"git push {repo_path} main:main 2>/dev/null; "
        f"RET=$?; "
        f"chmod +x {repo_path}/hooks/pre-receive 2>/dev/null; "
        f"exit $RET"
    )
    result = subprocess.run(
        ["docker", "exec", "-u", "git", "gitea", "sh", "-c", script],
        capture_output=True, text=True, timeout=30)
    return result.returncode == 0


def upload_file(branch: str, filepath: str, content: str, msg: str):
    # Validate branch at the boundary — it's interpolated into the Gitea
    # URL path and then into a ref query-param. Unicode or control chars
    # here would either break the request or produce a surprising commit
    # target. See issue #19.
    require_branch("branch", branch)
    # `filepath` is the target repo path (e.g. `src/foo.py`). Permissive
    # pattern allows `/` and `.` for directory trees. Length is the same
    # 128 cap as branch names.
    require_branch("filepath", filepath)

    b64 = base64.b64encode(content.encode()).decode()
    existing = gitea("GET", f"/api/v1/repos/{REPO}/contents/{filepath}?ref={branch}")
    sha = existing.get("sha", "")
    payload = {"content": b64, "message": msg, "branch": branch}
    if sha:
        payload["sha"] = sha
    gitea("POST", f"/api/v1/repos/{REPO}/contents/{filepath}", payload)


# ── Supervisor ──────────────────────────────────────────────────────────────

@dataclass
class SupervisorState:
    interventions: dict = field(default_factory=dict)  # task_id → count
    events: list = field(default_factory=list)  # log of what happened

    def record(self, task_id: str, action: str, detail: str):
        self.interventions[task_id] = self.interventions.get(task_id, 0) + 1
        self.events.append({
            "time": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "action": action,
            "detail": detail,
            "intervention_count": self.interventions[task_id],
        })
        print(f"  SUPERVISOR: [{action}] {detail}")


def run_agent_with_supervision(
    sandbox: str,
    project: str,
    prompt: str,
    task_id: str,
    issue_number: int,
    supervisor: SupervisorState,
    framework: str | None = None,
) -> tuple[str, bool]:
    """Run an agent with timeout and retry. Returns (stdout, success).

    Framework defaults to the project-configured FRAMEWORK (from
    CALORON_FRAMEWORK env var). Callers can override — e.g. per-task
    framework from the DAG — but the reviewer and fixer used to default
    to claude-code explicitly, which silently broke for projects
    configured with gemini-cli / codex-cli / etc.
    """
    # Validate at entry: `task_id` becomes a branch-name fragment and
    # an issue-body interpolation downstream. PO-generated ids that
    # drift from the expected pattern (shell metacharacters, unicode,
    # leading `-`) need to be caught here rather than at the git/gitea
    # boundary where the error is less recoverable. See issue #19.
    require_id("task_id", task_id)

    effective_framework = framework or FRAMEWORK

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            agent_cmd = build_agent_command(effective_framework, prompt)
            result = subprocess.run(
                [sandbox, project] + agent_cmd,
                capture_output=True, text=True,
                timeout=AGENT_TIMEOUT_S,
            )
            return result.stdout or "", True

        except subprocess.TimeoutExpired:
            count = supervisor.interventions.get(task_id, 0)

            if count == 0:
                # Probe: post a comment asking for status
                supervisor.record(task_id, "PROBE",
                    f"Agent timed out after {AGENT_TIMEOUT_S}s (attempt {attempt})")
                gitea("POST", f"/api/v1/repos/{REPO}/issues/{issue_number}/comments", {
                    "body": f"⚠️ **Supervisor probe:** Agent for task `{task_id}` has not responded "
                            f"after {AGENT_TIMEOUT_S}s. Retrying..."
                })

            elif count == 1:
                # Restart: try again with a simpler prompt
                supervisor.record(task_id, "RESTART",
                    "Agent stalled again after probe. Simplifying prompt.")
                gitea("POST", f"/api/v1/repos/{REPO}/issues/{issue_number}/comments", {
                    "body": f"🔄 **Supervisor restart:** Retrying task `{task_id}` with simplified context."
                })
                prompt = prompt.split("\n")[0]  # Keep only the first line

            else:
                # Escalate: give up and create escalation issue
                supervisor.record(task_id, "ESCALATE",
                    f"Agent failed after {count} interventions. Escalating to human.")
                gitea("POST", f"/api/v1/repos/{REPO}/issues", {
                    "title": f"🚨 Escalation: task {task_id} stalled",
                    "body": f"## Human intervention required\n\n"
                            f"**Task:** {task_id}\n"
                            f"**Issue:** #{issue_number}\n"
                            f"**Attempts:** {count + 1}\n\n"
                            f"The agent has timed out {count + 1} times.\n"
                            f"Comment `resolved` when fixed.",
                    "labels": [],
                })
                return "", False

    return "", False


# ── Feedback ────────────────────────────────────────────────────────────────

def post_feedback(
    issue_number: int,
    task_id: str,
    agent_role: str,
    task_clarity: int,
    blockers: list[str],
    tools_used: list[str],
    time_min: int,
    assessment: str,
    notes: str = "",
):
    """Post a caloron_feedback YAML comment on the issue."""
    blockers_yaml = "\n".join(f'    - "{b}"' for b in blockers) if blockers else "    []"
    tools_yaml = "\n".join(f'    - "{t}"' for t in tools_used)

    body = f"""---
caloron_feedback:
  task_id: "{task_id}"
  agent_role: "{agent_role}"
  task_clarity: {task_clarity}
  blockers:
{blockers_yaml}
  tools_used:
{tools_yaml}
  tokens_consumed: 0
  time_to_complete_min: {time_min}
  self_assessment: "{assessment}"
  notes: "{notes}"
---"""

    gitea("POST", f"/api/v1/repos/{REPO}/issues/{issue_number}/comments", {
        "body": body
    })


# ── Retro ───────────────────────────────────────────────────────────────────

def run_retro(issue_numbers: list[int], supervisor: SupervisorState, sprint_time_s: int,
              sprint_start_iso: str = ""):
    """Collect feedback from Gitea issues and compute retro."""
    print(f"=== RETRO ({BACKEND} backend) ===")
    print()

    # Collect feedback from issue comments
    feedbacks = []
    for issue_num in issue_numbers:
        comments = gitea("GET", f"/api/v1/repos/{REPO}/issues/{issue_num}/comments")
        if not isinstance(comments, list):
            continue
        for comment in comments:
            body = comment.get("body", "")
            if "caloron_feedback:" not in body:
                continue
            match = re.search(r"---\s*\n(.*?)\n---", body, re.DOTALL)
            if not match:
                continue
            try:
                import yaml
                parsed = yaml.safe_load(match.group(1))
                if parsed and "caloron_feedback" in parsed:
                    feedbacks.append(parsed["caloron_feedback"])
            except Exception:
                # Fallback: parse manually
                fb = {}
                for line in match.group(1).split("\n"):
                    line = line.strip()
                    if ":" in line and not line.startswith("-"):
                        key, _, val = line.partition(":")
                        key = key.strip()
                        val = val.strip().strip('"')
                        if key in ("task_clarity", "tokens_consumed", "time_to_complete_min"):
                            try: val = int(val)
                            except: pass
                        fb[key] = val
                if "task_id" in fb:
                    feedbacks.append(fb)

    # KPIs
    total = len(feedbacks)
    if total == 0:
        print("  No feedback collected!")
        return

    completed = sum(1 for f in feedbacks if f.get("self_assessment") == "completed")
    failed = sum(1 for f in feedbacks if f.get("self_assessment") in ("failed", "crashed"))
    blocked = sum(1 for f in feedbacks if f.get("self_assessment") == "blocked")

    clarities = [f.get("task_clarity", 0) for f in feedbacks if isinstance(f.get("task_clarity"), (int, float))]
    avg_clarity = sum(clarities) / len(clarities) if clarities else 0

    all_blockers = []
    for f in feedbacks:
        b = f.get("blockers", [])
        if isinstance(b, list):
            all_blockers.extend(b)

    print(f"  Tasks completed:      {completed}/{total}")
    print(f"  Failed/crashed:       {failed}")
    print(f"  Blocked:              {blocked}")
    print(f"  Avg clarity:          {avg_clarity:.1f}/10")
    print(f"  Sprint time:          {sprint_time_s}s")
    print(f"  Avg time/task:        {sprint_time_s // max(total, 1)}s")
    print(f"  Supervisor events:    {len(supervisor.events)}")

    # Blockers analysis
    if all_blockers:
        print(f"\n  Blockers ({len(all_blockers)}):")
        for b in all_blockers:
            print(f"    - {b}")

    # Per-task breakdown
    print("\n  Per-task:")
    for f in feedbacks:
        tid = f.get("task_id", "?")
        clarity = f.get("task_clarity", "?")
        time_min = f.get("time_to_complete_min", "?")
        assessment = f.get("self_assessment", "?")
        print(f"    {tid}: clarity={clarity}/10, time={time_min}min, assessment={assessment}")

    # Improvements
    improvements = []
    low_clarity = [f for f in feedbacks if isinstance(f.get("task_clarity"), (int, float)) and f["task_clarity"] < 5]
    if low_clarity:
        improvements.append(f"Improve task specifications — {len(low_clarity)} tasks had clarity < 5/10")

    if supervisor.events:
        improvements.append(f"Reduce agent stalls — {len(supervisor.events)} supervisor interventions")

    dep_blockers = [b for b in all_blockers if "depend" in b.lower() or "dag" in b.lower()]
    if dep_blockers:
        improvements.append(f"Fix DAG dependencies — {len(dep_blockers)} runtime deps discovered")

    if improvements:
        print("\n  Improvements:")
        for imp in improvements:
            print(f"    → {imp}")
    else:
        print("\n  No improvements needed — clean sprint!")

    # Noether-enhanced analysis (when using noether backend)
    if BACKEND == "noether" and feedbacks:
        print("\n  Noether analysis:")
        # Build feedback items for the stage
        feedback_items = [{"is_parsed_yaml": True, "parsed": f} for f in feedbacks]
        kpi_data = {
            "completion_rate": completed / total if total else 0,
            "avg_interventions": len(supervisor.events) / total if total else 0,
        }
        analysis = noether_analyze_feedback(feedback_items, kpi_data)
        if analysis:
            for theme in analysis.get("themes", []):
                print(f"    Theme: {theme}")
            for imp in analysis.get("improvements", []):
                print(f"    Improvement: {imp}")
            for learn in analysis.get("learnings", []):
                print(f"    Learning: {learn}")
            print(f"    Sentiment: {analysis.get('sentiment', '?')}")

            # Add Noether improvements to the list
            improvements.extend(analysis.get("improvements", []))

        # Generate report via Noether stage
        ended_at = datetime.now(UTC).isoformat()
        report = noether_write_report(
            "sprint", kpi_data, feedback_items, sprint_start_iso or ended_at, ended_at)
        if report and report.get("report_markdown"):
            report_path = os.path.join(WORK, "retro_report.md")
            Path(report_path).write_text(report["report_markdown"])
            print(f"\n  Report written to: {report_path}")

    # Supervisor log
    if supervisor.events:
        print("\n  Supervisor log:")
        for ev in supervisor.events:
            print(f"    [{ev['action']}] {ev['task_id']}: {ev['detail']}")

    # Save learnings for next sprint
    learnings = load_learnings()
    learnings["sprints"].append({
        "total": total,
        "completed": completed,
        "failed": failed,
        "avg_clarity": round(avg_clarity, 1),
        "supervisor_events": len(supervisor.events),
        "sprint_time_s": sprint_time_s,
        "blockers": all_blockers,
    })
    learnings["improvements"].extend(improvements)
    save_learnings(learnings)
    print(f"\n  Learnings saved ({len(learnings['sprints'])} sprints total)")

    print()


# ── Learnings ───────────────────────────────────────────────────────────────

def load_learnings() -> dict:
    """Load learnings from previous sprints."""
    if os.path.exists(LEARNINGS_FILE):
        return json.loads(Path(LEARNINGS_FILE).read_text())
    return {"sprints": [], "improvements": [], "po_context": ""}


def save_learnings(learnings: dict):
    """Save learnings for next sprint."""
    Path(LEARNINGS_FILE).write_text(json.dumps(learnings, indent=2))


_PO_CONTEXT_DETAILED_WINDOW = 2  # Last N sprints shown with full blocker lists


def build_po_context(learnings: dict) -> str:
    """Build context from previous sprints for the PO Agent.

    Uses a two-tier compression to prevent unbounded prompt growth —
    field report at sprint 3 showed the PO already at 9 min generation
    time and headed for PO_TIMEOUT at sprint 5-6:

    - The most recent ``_PO_CONTEXT_DETAILED_WINDOW`` sprints get full
      blocker lists + KPIs.
    - Sprints before that window get rolled into an aggregate summary:
      total tasks, completion rate, recurring blocker themes (deduped).
    - Force-merged blockers stay verbatim regardless of age since they
      represent unresolved technical debt.
    """
    if not learnings.get("sprints"):
        return ""

    sprints = learnings["sprints"]
    detailed = sprints[-_PO_CONTEXT_DETAILED_WINDOW:]
    older = sprints[:-_PO_CONTEXT_DETAILED_WINDOW] if len(sprints) > _PO_CONTEXT_DETAILED_WINDOW else []

    ctx = "\n## Learnings from Previous Sprints\n\n"

    # Aggregate summary of older sprints (compressed to prevent growth).
    if older:
        total = sum(s.get("total", 0) for s in older)
        completed = sum(s.get("completed", 0) for s in older)
        rate = (completed / total * 100) if total else 0
        ctx += (
            f"Historical ({len(older)} earlier sprint(s) compressed): "
            f"{completed}/{total} tasks completed ({rate:.0f}%). "
        )
        # Dedup + surface recurring blocker themes across older sprints.
        themes: dict[str, int] = {}
        for s in older:
            for b in s.get("blockers", []):
                # First 60 chars is enough to cluster; full text re-appears
                # in the detailed window if it was also recent.
                key = b[:60].strip().lower()
                themes[key] = themes.get(key, 0) + 1
        recurring = sorted(themes.items(), key=lambda kv: -kv[1])[:3]
        recurring = [(k, n) for k, n in recurring if n >= 2]
        if recurring:
            ctx += "Recurring themes:\n"
            for theme, count in recurring:
                ctx += f"  - ({count}×) {theme}\n"
        ctx += "\n"

    # Detailed window.
    ctx += f"Last {len(detailed)} sprint(s) in detail:\n"
    for s in detailed:
        ctx += (
            f"- {s.get('sprint_id', '?')}: "
            f"{s.get('completed', 0)}/{s.get('total', 0)} tasks, "
            f"clarity {s.get('avg_clarity', '?')}/10, "
            f"{s.get('supervisor_events', 0)} supervisor events\n"
        )
    ctx += "\n"

    last = sprints[-1]

    if learnings.get("improvements"):
        ctx += "Pending improvements (carry-forward):\n"
        for imp in learnings["improvements"][-8:]:
            ctx += f"- {imp}\n"
        ctx += "\n"

    # Surface force-merges — they represent real bugs that slipped through.
    force_merges = [b for b in last.get("blockers", []) if "FORCE-MERGED" in b]
    if force_merges:
        ctx += "⚠️ Unresolved feedback from force-merged PRs last sprint:\n"
        for b in force_merges:
            ctx += f"- {b}\n"
        ctx += (
            "Treat these as open technical debt — either surface them as "
            "dedicated tasks this sprint, or explicitly acknowledge in "
            "agent_prompts that the relevant module needs the fix.\n\n"
        )

    regular_blockers = [b for b in last.get("blockers", []) if "FORCE-MERGED" not in b]
    if regular_blockers:
        ctx += "Blockers from last sprint:\n"
        for b in regular_blockers[-8:]:
            ctx += f"- {b}\n"
        ctx += "\nAddress these in task specifications.\n"

    return ctx


def _resolved_skills_for(task: TaskDict) -> set[str]:
    """Collect the skills/tools the resolver actually attached to a task.

    Looks across three places because the code path differs depending on
    whether agentspec is installed and whether the bridge populated its
    own `tools` list:

      1. ``task["skills"]`` — from the HR agent (always present).
      2. ``task["agentspec"]["tools"]`` — from the bridge when agentspec
         is installed and resolution succeeded.
      3. ``task["tools_used"]`` — set by the HR agent too when it could
         map a skill to a concrete tool.

    Union of all three, lowercased for case-insensitive comparison.
    """
    out: set[str] = set()
    for key in ("skills", "tools_used"):
        val = task.get(key) or []
        if isinstance(val, list):
            out.update(str(v).lower() for v in val)
    agentspec_bridge = task.get("agentspec") or {}
    if isinstance(agentspec_bridge, dict):
        tools_val = agentspec_bridge.get("tools") or []
        if isinstance(tools_val, list):
            out.update(str(v).lower() for v in tools_val)
    return out


def _enforce_required_skills(
    tasks: list[TaskDict],
) -> tuple[list[TaskDict], list[BlockedTaskDict]]:
    """Split ``tasks`` into (runnable, blocked) by ``required_skills``.

    A task with ``required_skills: []`` or no field at all is always
    runnable. When the set is non-empty, every entry must appear in the
    task's resolved skills/tools (case-insensitive) or the task is
    blocked with a diagnostic record.

    Blocked tasks are NOT silently dropped — callers log them so the
    retro captures the config gap as a first-class blocker.
    """
    runnable: list[TaskDict] = []
    blocked: list[BlockedTaskDict] = []
    for task in tasks:
        required = task.get("required_skills") or []
        if not required:
            runnable.append(task)
            continue
        resolved = _resolved_skills_for(task)
        missing = [r for r in required if str(r).lower() not in resolved]
        if missing:
            blocked.append(
                BlockedTaskDict(
                    id=task.get("id", "?"),
                    required=list(required),
                    resolved=sorted(resolved),
                    missing=missing,
                    task=task,
                )
            )
        else:
            runnable.append(task)
    return runnable, blocked


def auto_po_timeout(sprint_count: int) -> int:
    """Scale the PO timeout with accumulated history.

    Field report: fixed 300s ceiling was fine at sprint 1-2 but at
    sprint 3 the PO already took ~9 minutes. Formula: 300s base + 60s
    per prior sprint, capped at 900s (15 min) so runaway runs still
    get killed.
    """
    return min(900, 300 + 60 * max(0, sprint_count))


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    goal = sys.argv[1] if len(sys.argv) > 1 else \
        "Build a Python module with functions to validate email addresses and phone numbers. Include comprehensive pytest tests."

    project = f"{WORK}/project"
    os.makedirs(f"{project}/src", exist_ok=True)
    os.makedirs(f"{project}/tests", exist_ok=True)

    # Init local workspace
    subprocess.run(["git", "init", "-q"], cwd=project, capture_output=True)
    subprocess.run(["git", "config", "user.name", "caloron"], cwd=project, capture_output=True)
    subprocess.run(["git", "config", "user.email", "bot@caloron.local"], cwd=project, capture_output=True)
    Path(f"{project}/src/__init__.py").write_text('"""Project."""\n')
    Path(f"{project}/tests/__init__.py").write_text("")
    subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
    subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=project) or \
        subprocess.run(["git", "commit", "-qm", "init"], cwd=project, capture_output=True)

    supervisor = SupervisorState()
    sprint_start = time.time()

    # Gitea preflight — silent-failure mode is the worst UX. Warn loudly.
    gitea_ok, gitea_detail = gitea_available()
    if not gitea_ok:
        sys.stderr.write(
            "\n"
            "⚠️  Gitea is not reachable.\n"
            f"   Reason: {gitea_detail}\n"
            "\n"
            "   Caloron sprints require a running Gitea container for issues,\n"
            "   PRs, and merges. Without it, sprints run but produce fake\n"
            "   issue numbers (#0) and no real version control.\n"
            "\n"
            "   Start one with:\n"
            "     docker run -d --name gitea -p 3000:3000 -p 222:22 gitea/gitea:1.22\n"
            "\n"
            "   Then re-run the sprint. Set CALORON_SKIP_GITEA_CHECK=1 to\n"
            "   bypass this check (sprints will still run but version control\n"
            "   calls will be no-ops).\n\n"
        )
        if not os.environ.get("CALORON_SKIP_GITEA_CHECK"):
            sys.exit(2)

    # Load learnings from previous sprints
    learnings = load_learnings()
    sprint_number = len(learnings["sprints"]) + 1
    po_context = build_po_context(learnings)

    # Loud log so users can see whether prior-sprint context actually
    # made it into this run — the #1 reported bug was "po_context silently
    # empty in sprint 2." Absence vs. presence is now visible on stdout.
    if po_context:
        print(
            f"  ✓ Loaded {len(learnings['sprints'])} prior sprint(s) "
            f"from {LEARNINGS_FILE}; PO context: {len(po_context)} chars"
        )
    else:
        print(
            f"  (no prior learnings at {LEARNINGS_FILE} — first sprint or "
            "fresh WORK directory)"
        )

    # Persist the generated context for post-hoc inspection.
    learnings["last_po_context"] = po_context
    save_learnings(learnings)

    # Load agent version store
    agent_store = AgentVersionStore(os.path.join(WORK, "agent_versions.json"))

    print("=" * 60)
    print(f"  FULL AUTONOMOUS SPRINT #{sprint_number}")
    print(f"  Backend: {BACKEND}")
    print(f"  Goal: {goal}")
    if BACKEND == "noether":
        print(f"  Stages: {NOETHER_STAGES_DIR}")
    if AGENTSPEC_AVAILABLE:
        print("  AgentSpec: enabled (manifest-based agent resolution)")
    else:
        # Loud warning — the HR-agent keyword fallback produces
        # strictly weaker agent selection than agentspec's manifest
        # resolver. Field reports surface this as mystery tool gaps;
        # make the downgrade impossible to miss. Set
        # CALORON_ALLOW_NO_AGENTSPEC=1 to silence if users genuinely
        # want keyword fallback (e.g. minimal CI environments).
        sys.stderr.write(
            "\n"
            "⚠️  AgentSpec is NOT installed.\n"
            "   Caloron is falling back to keyword-matching for agent\n"
            "   skill/tool/MCP selection, which is strictly weaker than\n"
            "   manifest-based resolution and was the root cause of\n"
            "   several previously-reported mystery tool gaps.\n"
            "\n"
            "   Install with:\n"
            "     pip install agentspec-alpibru\n"
            "\n"
            "   Silence this warning (if keyword fallback is intentional):\n"
            "     export CALORON_ALLOW_NO_AGENTSPEC=1\n"
            "\n"
        )
        if not os.environ.get("CALORON_ALLOW_NO_AGENTSPEC"):
            # Give the user a few seconds to abort; don't hard-fail
            # because the fallback does still work.
            print("  AgentSpec: MISSING — using keyword-match fallback")
        else:
            print("  AgentSpec: disabled (CALORON_ALLOW_NO_AGENTSPEC=1)")
    if po_context:
        print(f"  (with learnings from {len(learnings['sprints'])} previous sprint(s))")
    # Show agent versions if any exist
    if agent_store.agents:
        print(f"  Agents: {len(agent_store.agents)} with version history")
    print("=" * 60)
    print()

    # ── Step 1: PO Agent (or precomputed tasks from --graph) ────────────
    precomputed = os.environ.get("CALORON_PRECOMPUTED_TASKS", "")
    if precomputed and os.path.exists(precomputed):
        print(f"--- Step 1: Using precomputed tasks from {precomputed} ---")
        try:
            tasks = json.loads(Path(precomputed).read_text())
            if not isinstance(tasks, list) or not tasks:
                raise ValueError("precomputed tasks file must be a non-empty list")
        except Exception as e:
            print(f"  ERROR: could not load precomputed tasks: {e}")
            sys.exit(1)
        Path(f"{WORK}/dag.json").write_text(json.dumps(tasks, indent=2))
        for t in tasks:
            deps = ", ".join(t.get("depends_on", [])) or "none"
            print(f"  {t['id']}: {t['title']} (deps: {deps})")
        print()
        # Jump straight to Step 1.5 by falling through — skip the PO call.
        _skip_po = True
    else:
        _skip_po = False

    print("--- Step 1: PO Agent ---" if not _skip_po else "--- Skipping PO — tasks precomputed ---")
    available_frameworks = ", ".join(FRAMEWORKS.keys())
    po_prompt = f"""You are a Product Owner breaking a sprint goal into concrete agent tasks.

GOAL (read carefully and literally):
{goal}
{po_context}
How to decompose:

1. Read the goal as an ordered list of deliverables. If it explicitly
   enumerates N items (bugs to fix, features to add, files to touch),
   produce N tasks — one per item — not a fixed 2-3.
2. Classify the goal's intent before generating tasks:
   - "implement / build / create / add / fix" → implementation tasks
     that create or modify src/ (plus one test task only if the changes
     introduce new behaviour that needs coverage and the goal did not
     already list test work).
   - "test / cover / add tests for" → test-only tasks that exercise
     existing code; do NOT inject implementation work that wasn't asked
     for.
   - "refactor / clean up / simplify" → refactor tasks preserving
     behaviour; tests already exist and only change if behaviour does.
   - Mixed goals → mirror the structure of the goal.
3. If the goal lists bullet-pointed fixes or numbered items, each bullet
   becomes its own task. Don't collapse them into generic "fill gaps"
   buckets — the field report called this out as the main source of
   wasted cycles.
4. Task ids are short slugs derived from the item (e.g. fix-auth-token,
   add-rate-limit), not generic names like "impl" / "tests".
5. Project-level files (pyproject.toml, Dockerfile, config/,
   migrations/) are fair game — don't restrict to src/ and tests/.

Output ONLY a JSON array. Each task has:
- id: short slug tied to the item
- title: one-line description
- depends_on: list of task IDs ([] if none)
- agent_prompt: specific instructions (exact file paths, function
  signatures, expected behaviour, which bullet from the goal it
  addresses)
- framework: which tool to use (default: "{FRAMEWORK}"). Available: {available_frameworks}
- required_skills: list of skills the agent MUST have for this task
  (e.g. ["python-development", "github-pr-management"]). Omit or pass
  [] when no specific skill is load-bearing. When set, the sprint will
  abort this task before running if the resolved agent lacks any of
  them — surfacing the config gap instead of silently producing bad
  output.

Example for a goal listing 3 bug fixes:
[{{"id":"fix-auth-token","title":"Fix token refresh race","depends_on":[],"agent_prompt":"In src/auth.py... addresses goal bullet 1","framework":"{FRAMEWORK}"}},
 {{"id":"fix-rate-limit","title":"Honour 429 retry header","depends_on":[],"agent_prompt":"In src/http.py... addresses goal bullet 2","framework":"{FRAMEWORK}"}},
 {{"id":"fix-null-id","title":"Reject null user_id","depends_on":[],"agent_prompt":"In src/models.py... addresses goal bullet 3","framework":"{FRAMEWORK}"}}]

Example for a goal "add tests for the payment module":
[{{"id":"tests-payment-happy","title":"Tests: payment happy path","depends_on":[],"agent_prompt":"tests/test_payment.py covering successful charge, capture, refund...","framework":"{FRAMEWORK}"}},
 {{"id":"tests-payment-edges","title":"Tests: payment edge cases","depends_on":[],"agent_prompt":"tests/test_payment.py covering declined card, network timeout, duplicate idempotency key...","framework":"{FRAMEWORK}"}}]

Do not inflate to 2-3 tasks if the goal is smaller; do not collapse to
2-3 if the goal is bigger.{_conventions_block(CONVENTIONS)}"""

    if not _skip_po:
        po_cmd = build_agent_command(FRAMEWORK, po_prompt)
        effective_po_timeout = (
            auto_po_timeout(len(learnings.get("sprints", [])))
            if PO_TIMEOUT_AUTO
            else PO_TIMEOUT_S
        )
        if os.environ.get("CALORON_DEBUG"):
            sys.stderr.write(
                f"\n=== PO PROMPT (CALORON_DEBUG) ===\n{po_prompt}\n"
                f"=== / PO PROMPT (timeout={effective_po_timeout}s"
                f"{', auto-scaled' if PO_TIMEOUT_AUTO else ''}) ===\n\n"
            )
        po_result = subprocess.run(
            [SANDBOX, project] + po_cmd,
            capture_output=True, text=True, timeout=effective_po_timeout)
        po_out = po_result.stdout or ""

        match = re.search(r"\[.*\]", po_out, re.DOTALL)
        if not match:
            print("  ERROR: PO produced no JSON")
            sys.exit(1)
        tasks = json.loads(match.group())
        Path(f"{WORK}/dag.json").write_text(json.dumps(tasks, indent=2))

        for t in tasks:
            deps = ", ".join(t.get("depends_on", [])) or "none"
            print(f"  {t['id']}: {t['title']} (deps: {deps})")

    # ── Step 1.5: AgentSpec resolve (or HR Agent fallback) ───────────────
    print()
    skill_store = SkillStore(os.path.join(WORK, "skill_store.json"))

    if AGENTSPEC_AVAILABLE:
        print("--- AgentSpec: Resolving agents ---")
        agents_dir = os.path.join(WORK, "agents")
        tasks = run_hr_agent(tasks, skill_store, preferred_framework=FRAMEWORK)
        tasks = enrich_tasks_with_agentspec(
            tasks, preferred_framework=FRAMEWORK, agents_dir=agents_dir)
        print_agentspec_assignments(tasks)
    else:
        print("--- HR Agent: Assigning skills (agentspec not available) ---")
        tasks = run_hr_agent(tasks, skill_store, preferred_framework=FRAMEWORK)
        print_assignments(tasks)

    # ── Step 1.6: Required-skills enforcement ────────────────────────────
    # Tasks may declare `required_skills`: a list the resolved agent MUST
    # have, or the task is blocked before it runs. Previously the HR
    # agent / agentspec bridge tracked missing tools advisorily but never
    # stopped a sprint — users saw mystery "agent didn't use X" failures
    # on tasks that needed a tool that just wasn't in the environment.
    # Now: fail-fast with a clear error.
    tasks, blocked_tasks = _enforce_required_skills(tasks)
    if blocked_tasks:
        print()
        print("--- ⚠️  Required-skills enforcement ---")
        for bt in blocked_tasks:
            print(
                f"  BLOCKED {bt['id']}: missing {bt['missing']} "
                f"(required: {bt['required']}, resolved: {bt['resolved']})"
            )
        if not tasks:
            sys.stderr.write(
                "\nAll tasks blocked by required-skills check. Aborting sprint.\n"
                "Fix the environment (install missing CLIs / MCPs / API keys)\n"
                "or adjust the PO's required_skills declarations.\n"
            )
            sys.exit(3)
        print(
            f"  Continuing with {len(tasks)} unblocked task(s); "
            f"{len(blocked_tasks)} will be reported as blockers in retro.\n"
        )

    # Register agents in version store (or load existing versions)
    print()
    print("  Agents:")
    for t in tasks:
        tid = t["id"]
        spec = {
            "personality": "developer",
            "model": t.get("model", "balanced"),
            "framework": t.get("framework", FRAMEWORK),
            "capabilities": t.get("capabilities", ["code-writing", "python"]),
            "extra_instructions": "",
        }
        version = agent_store.register(tid, spec, f"sprint-{sprint_number}")

        # If agent has evolved, use the latest version's spec
        current = agent_store.current(tid)
        if current and current["version"] != "1.0":
            t["framework"] = current.get("framework", t.get("framework", FRAMEWORK))
            # Prepend evolved instructions to agent prompt
            evolved_instructions = current.get("extra_instructions", "")
            if evolved_instructions:
                t["agent_prompt"] = f"{evolved_instructions}\n\n{t.get('agent_prompt', t['title'])}"
            print(f"    {tid}: v{current['version']} (evolved — {current['model']}, [{', '.join(current.get('capabilities', []))}])")
        else:
            print(f"    {tid}: v{version} (new)")
    print()

    # ── Step 2: Create issues ───────────────────────────────────────────
    print("--- Step 2: Issues ---")
    issue_map = {}  # task_id → issue_number
    for t in tasks:
        result = gitea("POST", f"/api/v1/repos/{REPO}/issues", {
            "title": t["title"],
            "body": f"**Task:** {t['id']}\n**Depends on:** {', '.join(t.get('depends_on', [])) or 'none'}",
        })
        num = result.get("number", 0)
        issue_map[t["id"]] = num
        print(f"  Issue #{num}: {t['title']}")
    print()

    # ── Step 3-7: Execute tasks ─────────────────────────────────────────
    print("--- Step 3: Execute ---")
    print()

    completed = set()
    remaining = list(tasks)
    feedback_data = []

    while remaining:
        ready = [t for t in remaining if all(d in completed for d in t.get("depends_on", []))]
        if not ready:
            print("STUCK — unresolvable dependencies!")
            break

        for task in ready:
            tid = task["id"]
            title = task["title"]
            prompt = task.get("agent_prompt", title)
            framework = task.get("framework", FRAMEWORK)
            issue_num = issue_map.get(tid, 0)
            task_start = time.time()
            blockers = []

            print(f"{'=' * 50}")
            print(f"  Task: {tid} — {title}")
            print(f"  Issue: #{issue_num} | Framework: {framework}")
            print(f"{'=' * 50}")

            # Scaffold project from template (if first task and project is empty)
            task_text = f"{task.get('title', '')} {task.get('agent_prompt', '')}"
            scaffold = scaffold_project(project, task.get("skills", []), task_text)
            if scaffold.get("files"):
                print(f"  Scaffold: {scaffold['template_name']} ({len(scaffold['files'])} files)")

            # Configure the agent's worktree with skill-specific files
            if task.get("agentspec") and "error" not in task["agentspec"]:
                config_result = configure_agent_from_spec(project, task)
                config_result.get("extra_flags", [])
                files = config_result.get("files_written", [])
                if files:
                    print(f"  AgentSpec config: {', '.join(files)}")
            else:
                config_result = configure_agent(project, task, framework)
                config_result.get("extra_flags", [])
                print_config_summary(project, framework)

            # Agent writes code (with supervisor timeout)
            full_prompt = f"""{prompt}

Rules:
- Prefer src/ and tests/ for application code and tests
- Project-level files are fair game when the task needs them:
  pyproject.toml, Dockerfile, docker-compose.yml, .env.example,
  config/, scripts/, .github/workflows/, migrations/
- Do NOT modify caloron's own orchestration files (.caloron/, CLAUDE.md)
- Use type hints
- Read CLAUDE.md for skill-specific instructions
- When COMPLETELY done, output a feedback block as the LAST thing you print, in this exact format:

CALORON_FEEDBACK_START
{{
  "task_clarity": <1-10 how clear was the task description>,
  "blockers": [<list of strings describing what slowed you down or was unclear>],
  "tools_used": [<list of tools/libraries you used>],
  "self_assessment": "<completed|partial|blocked|failed>",
  "notes": "<any observations about the task>"
}}
CALORON_FEEDBACK_END{_conventions_block(CONVENTIONS)}"""

            print(f"  Agent running ({framework}, sandboxed, supervised)...")
            agent_out, success = run_agent_with_supervision(
                SANDBOX, project, full_prompt, tid, issue_num, supervisor, framework)

            # Parse agent's self-reported feedback
            agent_feedback = parse_agent_feedback(agent_out if success else "")

            if not success:
                blockers.append("Agent timed out and was escalated")
                assessment = "failed"
            else:
                assessment = agent_feedback.get("self_assessment", "completed")
                # Use agent-reported blockers
                agent_blockers = agent_feedback.get("blockers", [])
                if agent_blockers:
                    blockers.extend(agent_blockers)
                for line in agent_out.strip().split("\n")[-2:]:
                    if "CALORON_FEEDBACK" not in line:
                        print(f"    {line}")

            # Collect changed files
            subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
            diff = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                  cwd=project, capture_output=True, text=True)
            changed = [f for f in diff.stdout.strip().split("\n")
                       if f
                       and not _is_caloron_managed(f)
                       and f not in ("src/__init__.py", "tests/__init__.py")
                       and "__pycache__" not in f and not f.endswith(".pyc")]
            subprocess.run(["git", "checkout", "--", "."], cwd=project, capture_output=True)

            if changed and success:
                # Create branch
                branch = f"agent/{tid}"
                gitea("POST", f"/api/v1/repos/{REPO}/branches", {
                    "new_branch_name": branch, "old_branch_name": "main"
                })

                # Upload files
                for filepath in changed:
                    full_path = os.path.join(project, filepath)
                    if os.path.exists(full_path):
                        try:
                            content = open(full_path).read()
                        except (UnicodeDecodeError, ValueError):
                            continue  # skip binary files
                        upload_file(branch, filepath, content, f"[{tid}] {filepath}")
                        print(f"  Uploaded: {filepath}")

                # Create PR
                pr = gitea("POST", f"/api/v1/repos/{REPO}/pulls", {
                    "title": f"[{tid}] {title}",
                    "body": f"Closes #{issue_num}\n\nAgent: caloron-agent-{tid}",
                    "head": branch,
                    "base": "main",
                })
                pr_num = pr.get("number", "?")
                print(f"  PR #{pr_num}")

                # Review cycle — up to MAX_REVIEW_CYCLES attempts
                MAX_REVIEW_CYCLES = 3
                merged = False
                fix_reason = ""

                for review_cycle in range(1, MAX_REVIEW_CYCLES + 1):
                    # Reviewer agent (supervised)
                    print(f"  Reviewer (cycle {review_cycle})...")
                    review_prompt = f"""Review code change for: {title}
Files changed: {', '.join(changed)}
Check: correctness, tests, type hints, AND compliance with the
organisation conventions below (if any).
Respond ONLY: APPROVED or CHANGES_NEEDED: reason{_conventions_block(CONVENTIONS)}"""

                    review_out, review_ok = run_agent_with_supervision(
                        SANDBOX, project, review_prompt, f"{tid}-review-{review_cycle}",
                        issue_num, supervisor, framework=framework)
                    review = review_out.strip().split("\n")[-1] if review_out else "APPROVED"
                    print(f"  Review: {review[:80]}")

                    # Post review comment on PR
                    gitea("POST", f"/api/v1/repos/{REPO}/issues/{pr_num}/comments", {
                        "body": f"**Code Review (cycle {review_cycle}):** {review}"
                    })

                    if "CHANGES_NEEDED" not in review.upper():
                        # Approved — merge
                        merge_ok = git_merge_branch(branch, f"Merge PR #{pr_num}: [{tid}] {title}")
                        if merge_ok:
                            gitea("POST", f"/api/v1/repos/{REPO}/pulls/{pr_num}/merge", {"Do": "merge"})
                            print(f"  PR #{pr_num} MERGED ✓")
                            merged = True
                        else:
                            print("  Merge FAILED — branch may have conflicts")
                        break

                    # Changes requested — agent fixes
                    fix_reason = review.split("CHANGES_NEEDED:")[-1].strip() if ":" in review else review
                    blockers.append(f"Review cycle {review_cycle}: {fix_reason}")
                    print(f"  Agent fixing: {fix_reason[:60]}...")

                    fix_prompt = f"""The reviewer requested changes on your code for: {title}

Reviewer feedback: {fix_reason}

Files to fix: {', '.join(changed)}

Please fix the issues described above. Modify whatever files are needed
(src/, tests/, and project-level files like pyproject.toml, Dockerfile,
or config/ are all fair game). When done, stop.{_conventions_block(CONVENTIONS)}"""

                    fix_out, fix_ok = run_agent_with_supervision(
                        SANDBOX, project, fix_prompt, f"{tid}-fix-{review_cycle}",
                        issue_num, supervisor, framework=framework)
                    if fix_out:
                        for line in fix_out.strip().split("\n")[-2:]:
                            print(f"    {line}")

                    # Upload fixed files to the same branch
                    subprocess.run(["git", "add", "-A"], cwd=project, capture_output=True)
                    fix_diff = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                              cwd=project, capture_output=True, text=True)
                    fix_changed = [f for f in fix_diff.stdout.strip().split("\n")
                                   if f
                                   and not _is_caloron_managed(f)
                                   and f not in ("src/__init__.py", "tests/__init__.py")
                                   and "__pycache__" not in f and not f.endswith(".pyc")]
                    subprocess.run(["git", "checkout", "--", "."], cwd=project, capture_output=True)

                    for filepath in fix_changed:
                        full_path = os.path.join(project, filepath)
                        if os.path.exists(full_path):
                            try:
                                content = open(full_path).read()
                            except (UnicodeDecodeError, ValueError):
                                continue
                            upload_file(branch, filepath, content, f"[{tid}] fix: {filepath}")
                    print(f"  Pushed fix ({len(fix_changed)} files)")

                if not merged and review_cycle == MAX_REVIEW_CYCLES:
                    # Force merge after max cycles. The blocker string is
                    # prefixed with "⚠️ FORCE-MERGED" so build_po_context
                    # can surface it separately in the next sprint's
                    # retro — distinguishing "approved" from "merged over
                    # unresolved feedback" which used to look identical.
                    print("  Max review cycles reached — force merging")
                    merge_ok = git_merge_branch(branch, f"Merge PR #{pr_num}: [{tid}] {title} (force after {MAX_REVIEW_CYCLES} cycles)")
                    if merge_ok:
                        print(f"  ⚠️  PR #{pr_num} FORCE MERGED (unresolved review feedback)")
                    blockers.append(
                        f"⚠️ FORCE-MERGED after {MAX_REVIEW_CYCLES} review cycles — unresolved: "
                        f"{(fix_reason or 'unknown')[:160]}"
                    )

            task_time = int(time.time() - task_start)
            task_time_min = max(1, task_time // 60)

            # Post feedback on the issue
            # Use agent's self-reported feedback (not hardcoded guesses)
            reported_clarity = agent_feedback.get("task_clarity", 5)
            reported_tools = agent_feedback.get("tools_used", ["claude-code"])
            reported_notes = agent_feedback.get("notes", "")

            post_feedback(
                issue_number=issue_num,
                task_id=tid,
                agent_role="developer",
                task_clarity=reported_clarity,
                blockers=blockers,
                tools_used=reported_tools,
                time_min=task_time_min,
                assessment=assessment,
                notes=f"{reported_notes} | Files: {', '.join(changed) if changed else 'none'}. Time: {task_time}s.",
            )
            print(f"  Feedback: clarity={reported_clarity}/10, assessment={assessment}, "
                  f"blockers={len(blockers)}, tools={reported_tools}")

            feedback_data.append({
                "task_id": tid, "time_s": task_time, "files": changed,
                "assessment": assessment, "blockers": blockers,
                "clarity": reported_clarity,
                "tools": reported_tools,
                "notes": reported_notes,
            })

            completed.add(tid)
            remaining.remove(task)
            print(f"  Done ({task_time}s)")
            print()

    sprint_time = int(time.time() - sprint_start)

    # ── Step 8: Retro ───────────────────────────────────────────────────
    print()
    sprint_start_iso = datetime.fromtimestamp(sprint_start, tz=UTC).isoformat()
    run_retro(list(issue_map.values()), supervisor, sprint_time, sprint_start_iso)

    # ── Step 9: Auto-evolve agents based on retro ──────────────────────
    print("--- Step 9: Agent Evolution ---")

    # Build retro summary for evolution decisions
    total_tasks = len(feedback_data)
    failed_tasks = sum(1 for f in feedback_data if f["assessment"] == "failed")
    all_blockers = []
    for f in feedback_data:
        all_blockers.extend(f.get("blockers", []))

    # Use agent-reported clarity (not hardcoded guesses)
    clarities = [f.get("clarity", 5) for f in feedback_data]
    avg_clarity = sum(clarities) / len(clarities) if clarities else 5

    retro_summary = {
        "avg_clarity": avg_clarity,
        "failure_rate": failed_tasks / max(total_tasks, 1),
        "supervisor_events": len(supervisor.events),
        "avg_review_cycles": sum(1 for f in feedback_data if f.get("blockers")) / max(total_tasks, 1),
        "blockers": all_blockers,
    }

    # Record agent-reported performance for each agent
    for f in feedback_data:
        agent_store.record_performance(f["task_id"], {
            "clarity": f.get("clarity", 5),
            "completion_rate": 1.0 if f["assessment"] == "completed" else 0.0,
            "review_cycles": 1 + len(f.get("blockers", [])),
            "time_s": f["time_s"],
            "tools": f.get("tools", []),
            "notes": f.get("notes", ""),
        })

    # Auto-evolve (legacy agent_versioning)
    changes = auto_evolve_agents(agent_store, retro_summary, f"sprint-{sprint_number}")
    if not changes:
        print("  No evolution needed (legacy) — agents performing well")

    # AgentSpec-based evolution (produces versioned .agent files)
    if AGENTSPEC_AVAILABLE:
        print()
        print("  AgentSpec evolution:")
        agents_dir = os.path.join(WORK, "agents")
        agentspec_evolutions = auto_evolve_with_agentspec(
            tasks, retro_summary, feedback_data,
            f"sprint-{sprint_number}", agents_dir)
        print_evolution_summary(agentspec_evolutions)
    print()

    # ── Step 9b: Agent Profiles (signed portfolio) ──────────────────
    if PROFILES_AVAILABLE and AGENTSPEC_AVAILABLE:
        print("--- Agent Profiles ---")
        profiles_dir = os.path.join(WORK, "profiles")
        profile_mgr = ProfileManager(profiles_dir)

        for f in feedback_data:
            tid = f["task_id"]
            # Load or create profile from the task's agentspec manifest
            task_data = next((t for t in tasks if t.get("id") == tid), {})
            spec = task_data.get("agentspec", {})

            from agentspec.parser.manifest import AgentManifest
            try:
                manifest = AgentManifest(
                    name=f"caloron-agent-{tid}",
                    version="1.0.0",
                    description=task_data.get("title", ""),
                )
                profile = profile_mgr.load_or_create(manifest)

                result = profile_mgr.process_retro(profile, f,
                    sprint_id=f"sprint-{sprint_number}",
                    project=goal[:50] if goal else "")

                print(f"  {tid}: {result['memories_added']} memories, "
                      f"{result['skills_added']} skills, "
                      f"{result['memories_signed']} signed")
            except Exception as e:
                print(f"  {tid}: profile error — {e}")

        # Print profile summaries
        print()
        for f in feedback_data:
            tid = f["task_id"]
            profile = profile_mgr.load_profile(f"caloron-agent-{tid}")
            if profile:
                profile_mgr.print_profile_summary(profile)
                print()
    elif PROFILES_AVAILABLE:
        print("--- Agent Profiles: agentspec not available ---")
    print()

    # Show agent history
    print("--- Agent Versions ---")
    for agent_id in agent_store.agents:
        print_agent_history(agent_store, agent_id)

    # ── Gitea state ─────────────────────────────────────────────────────
    print("--- Gitea State ---")
    prs = gitea("GET", f"/api/v1/repos/{REPO}/pulls?state=all&limit=50")
    if isinstance(prs, list):
        print("PRs:")
        for pr in sorted(prs, key=lambda x: x.get("number", 0)):
            state = "merged" if pr.get("merged") else pr["state"]
            print(f"  PR #{pr['number']}: {pr['title']} [{state}]")

    issues = gitea("GET", f"/api/v1/repos/{REPO}/issues?state=all&type=issues&limit=50")
    if isinstance(issues, list):
        print("Issues:")
        for i in sorted(issues, key=lambda x: x.get("number", 0)):
            print(f"  #{i['number']}: {i['title']} [{i['state']}] ({i.get('comments', 0)} comments)")

    # ── Step 10: Post-sprint deploy ────────────────────────────────────
    print()
    print("--- Step 10: Deploy ---")
    deploy_result = post_sprint_deploy(project, f"sprint-{sprint_number}")
    print_deploy_summary(deploy_result)

    print("=" * 60)
    print(f"  SPRINT COMPLETE — {sprint_time}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
