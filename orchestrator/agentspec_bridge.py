"""
AgentSpec Bridge — converts PO task dicts into .agent manifests,
resolves them against the environment, and configures agent worktrees.

Replaces the HR Agent keyword matching + Agent Configurator with
AgentSpec's resolver for environment-aware agent configuration.

Usage in orchestrator.py:
    from agentspec_bridge import enrich_tasks_with_agentspec, configure_agent_from_spec

The bridge is additive — it enriches task dicts with agentspec data
but preserves backward compatibility with the existing skill_store flow.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from agentspec import AgentManifest, load_agent, resolve, ResolvedPlan, agent_hash
    from agentspec.parser.manifest import (
        BehaviorSpec,
        ModelSpec,
        ObservabilitySpec,
        ToolsSpec,
        TrustSpec,
    )
    AGENTSPEC_AVAILABLE = True
except ImportError:
    AGENTSPEC_AVAILABLE = False


# ── Task → .agent conversion ──────────────────────────────────────────────────

# Map caloron model tiers to agentspec capability levels
MODEL_TIER_MAP = {
    "strong": "reasoning-high",
    "balanced": "reasoning-mid",
    "fast": "reasoning-low",
}

# Map caloron skill names to agentspec abstract skills
SKILL_MAP = {
    "python-development": "code-execution",
    "typescript-development": "code-execution",
    "rust-development": "code-execution",
    "pytest-testing": "code-execution",
    "jest-testing": "code-execution",
    "data-analysis-pandas": "data-analysis",
    "rest-api-development": "code-execution",
    "sql-database": "code-execution",
    "web-search": "web-search",
    "browser-automation": "browser",
    "web-scraping": "code-execution",
    "git-operations": "git",
    "github-pr-management": "github",
    "docker-management": "code-execution",
    "kubernetes-management": "code-execution",
    "ota-pricing-analysis": "data-analysis",
    "charging-optimization": "code-execution",
    "slack-messaging": "code-execution",
    "jira-management": "code-execution",
    "noether-compose": "code-execution",
}

# Map caloron skills to MCP tools
MCP_SKILL_MAP = {
    "github-pr-management": "github",
    "sql-database": "postgres",
    "slack-messaging": "slack",
    "jira-management": "jira",
    "noether-compose": "noether",
}


def task_to_manifest(task: dict[str, Any], preferred_framework: str = "claude-code") -> AgentManifest:
    """Convert a PO-generated task dict into an AgentSpec manifest.

    The manifest captures: model capability, skills, tools, trust, behavior.
    """
    title = task.get("title", "agent")
    tid = task.get("id", "agent")
    prompt = task.get("agent_prompt", "")
    caloron_model = task.get("model", "balanced")
    caloron_skills = task.get("skills", [])
    caloron_creds = task.get("credentials", [])
    caloron_mcps = task.get("mcp_urls", [])

    # Map skills to agentspec abstract skills (deduplicated)
    abstract_skills = list(dict.fromkeys(
        SKILL_MAP.get(s, "code-execution") for s in caloron_skills
    ))
    # Always include file ops
    for base in ["file-read", "file-write"]:
        if base not in abstract_skills:
            abstract_skills.append(base)

    # Map skills to MCP tools
    mcp_tools: list[str | dict[str, Any]] = []
    for s in caloron_skills:
        if s in MCP_SKILL_MAP:
            mcp_tools.append(MCP_SKILL_MAP[s])

    # Add explicit MCP URLs from HR Agent
    for mcp in caloron_mcps:
        name = mcp.get("name", "")
        url = mcp.get("url", "")
        if name and url:
            mcp_tools.append({name: {"url": url}})

    # Build preferred model list based on framework
    preferred_models = _framework_preferred_models(preferred_framework)

    # Build behavior from task prompt
    traits = ["think-step-by-step", "be-concise"]
    if any(kw in prompt.lower() for kw in ["test", "pytest", "jest"]):
        traits.append("test-first")
    if any(kw in prompt.lower() for kw in ["review", "refactor"]):
        traits.append("self-review")

    manifest = AgentManifest(
        apiVersion="agent/v1",
        name=f"caloron-agent-{tid}",
        version="1.0.0",
        description=title,
        tags=caloron_skills[:5],
        model=ModelSpec(
            capability=MODEL_TIER_MAP.get(caloron_model, "reasoning-mid"),
            preferred=preferred_models,
            fallback="reasoning-low",
        ),
        skills=abstract_skills,
        tools=ToolsSpec(
            mcp=mcp_tools,
            native=["bash"],
        ),
        behavior=BehaviorSpec(
            persona=f"developer-{tid}",
            traits=traits,
            temperature=0.2,
            max_steps=50,
            on_error="retry",
            system_override=prompt[:500] if prompt else None,
        ),
        trust=TrustSpec(
            filesystem="scoped",
            scope=["./src", "./tests"],
            network="allowed",
            exec="sandboxed",
        ),
        observability=ObservabilitySpec(
            trace=True,
            step_limit=50,
        ),
    )

    return manifest


def _framework_preferred_models(framework: str) -> list[str]:
    """Build a model preference list based on the target framework."""
    models_by_framework = {
        "claude-code": [
            "claude/claude-sonnet-4-6",
            "claude/claude-haiku-4-5",
        ],
        "gemini-cli": [
            "gemini/gemini-2.5-pro",
            "gemini/gemini-2.0-flash",
        ],
        "codex-cli": [
            "openai/o3",
            "openai/gpt-4o",
        ],
        "aider": [
            "claude/claude-sonnet-4-6",
            "openai/gpt-4o",
        ],
        "open-code": [
            "claude/claude-sonnet-4-6",
            "openai/gpt-4o",
        ],
    }
    # Start with the framework's preferred models, then add others as fallbacks
    preferred = models_by_framework.get(framework, [])
    # Add cross-framework fallbacks
    all_models = [
        "claude/claude-sonnet-4-6",
        "gemini/gemini-2.5-pro",
        "openai/o3",
        "local/llama3:70b",
    ]
    for m in all_models:
        if m not in preferred:
            preferred.append(m)
    return preferred


# ── Enrichment (replaces HR Agent) ────────────────────────────────────────────


def enrich_tasks_with_agentspec(
    tasks: list[dict[str, Any]],
    preferred_framework: str = "claude-code",
    agents_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Enrich PO tasks with agentspec resolution.

    For each task:
    1. Convert to .agent manifest
    2. Resolve against the environment
    3. Attach resolved plan to the task dict

    This replaces both the HR Agent (skill assignment) and the model
    selection heuristics.
    """
    if not AGENTSPEC_AVAILABLE:
        print("  WARNING: agentspec not installed, falling back to HR Agent")
        return tasks

    # Create agents directory for .agent files
    if agents_dir:
        Path(agents_dir).mkdir(parents=True, exist_ok=True)

    enriched = []
    for task in tasks:
        manifest = task_to_manifest(task, preferred_framework)

        # Save .agent file for traceability
        if agents_dir:
            agent_file = Path(agents_dir) / f"{task.get('id', 'agent')}.agent"
            _save_manifest_yaml(manifest, agent_file)

        # Resolve against environment
        try:
            plan = resolve(manifest, verbose=True)
            task = {
                **task,
                "agentspec": {
                    "manifest_name": manifest.name,
                    "hash": agent_hash(manifest),
                    "runtime": plan.runtime,
                    "model": plan.model,
                    "tools": plan.tools,
                    "missing_tools": plan.missing_tools,
                    "auth_source": plan.auth_source,
                    "system_prompt": plan.system_prompt,
                    "warnings": plan.warnings,
                    "decisions": plan.decisions,
                },
                # Override framework with resolved runtime
                "framework": _runtime_to_framework(plan.runtime),
                "model": _capability_to_tier(manifest.model.capability),
            }
        except RuntimeError as exc:
            # Resolver failed — keep original task, add warning
            task = {
                **task,
                "agentspec": {
                    "error": str(exc),
                    "manifest_name": manifest.name,
                },
            }

        enriched.append(task)

    return enriched


def _runtime_to_framework(runtime: str) -> str:
    """Map agentspec runtime names back to caloron framework names."""
    mapping = {
        "claude-code": "claude-code",
        "gemini-cli": "gemini-cli",
        "codex-cli": "codex-cli",
        "opencode": "open-code",
        "aider": "aider",
        "ollama": "claude-code",  # fallback
        "cursor": "claude-code",  # fallback
    }
    return mapping.get(runtime, "claude-code")


def _capability_to_tier(capability: str) -> str:
    """Map agentspec capability back to caloron model tier."""
    mapping = {
        "reasoning-max": "strong",
        "reasoning-high": "strong",
        "reasoning-mid": "balanced",
        "reasoning-low": "fast",
    }
    return mapping.get(capability, "balanced")


# ── Agent configuration (replaces Agent Configurator) ─────────────────────────


def configure_agent_from_spec(
    worktree: str,
    task: dict[str, Any],
) -> dict[str, Any]:
    """Configure an agent's worktree using the agentspec resolved plan.

    Writes framework-specific config files based on the resolver's output.
    Falls back to agent_configurator.configure_agent() if agentspec data
    is not present.
    """
    spec = task.get("agentspec")
    if not spec or "error" in spec:
        # Fallback to legacy configurator
        from agent_configurator import configure_agent
        return configure_agent(worktree, task, task.get("framework", "claude-code"))

    runtime = spec.get("runtime", "claude-code")
    system_prompt = spec.get("system_prompt", "")
    tools = spec.get("tools", [])
    mcp_tools = [t for t in tools if isinstance(t, str) and t.startswith("mcp:")]

    result: dict[str, Any] = {"files_written": [], "extra_flags": []}

    # Write framework-specific config
    if runtime == "claude-code":
        _write_claude_config(worktree, system_prompt, mcp_tools, result)
    elif runtime == "gemini-cli":
        _write_gemini_config(worktree, system_prompt, mcp_tools, result)
    elif runtime == "codex-cli":
        _write_codex_config(worktree, system_prompt, mcp_tools, result)
    elif runtime in ("opencode", "open-code"):
        _write_opencode_config(worktree, system_prompt, mcp_tools, result)
    elif runtime == "aider":
        _write_aider_config(worktree, system_prompt, result)

    return result


def _write_claude_config(
    worktree: str, system_prompt: str, mcp_tools: list[str], result: dict[str, Any]
) -> None:
    claude_md = Path(worktree) / "CLAUDE.md"
    claude_md.write_text(f"""# Agent Instructions (generated by AgentSpec)

{system_prompt}

## Rules
- Only create/modify files in src/ and tests/
- Use type hints
- Run tests before finishing
""")
    result["files_written"].append("CLAUDE.md")

    if mcp_tools:
        mcp_config = {"mcpServers": {}}
        for tool in mcp_tools:
            name = tool.replace("mcp:", "")
            mcp_config["mcpServers"][name] = {"command": name, "args": []}
        mcp_path = Path(worktree) / ".mcp.json"
        mcp_path.write_text(json.dumps(mcp_config, indent=2))
        result["files_written"].append(".mcp.json")


def _write_gemini_config(
    worktree: str, system_prompt: str, mcp_tools: list[str], result: dict[str, Any]
) -> None:
    gemini_md = Path(worktree) / "GEMINI.md"
    gemini_md.write_text(f"""# Agent Instructions (generated by AgentSpec)

{system_prompt}
""")
    result["files_written"].append("GEMINI.md")

    if mcp_tools:
        settings = {"mcpServers": {}}
        for tool in mcp_tools:
            name = tool.replace("mcp:", "")
            settings["mcpServers"][name] = {"command": name, "args": []}
        settings_dir = Path(worktree) / ".gemini"
        settings_dir.mkdir(exist_ok=True)
        (settings_dir / "settings.json").write_text(json.dumps(settings, indent=2))
        result["files_written"].append(".gemini/settings.json")


def _write_codex_config(
    worktree: str, system_prompt: str, mcp_tools: list[str], result: dict[str, Any]
) -> None:
    agents_md = Path(worktree) / "AGENTS.md"
    agents_md.write_text(f"""# Agent Instructions (generated by AgentSpec)

{system_prompt}
""")
    result["files_written"].append("AGENTS.md")


def _write_opencode_config(
    worktree: str, system_prompt: str, mcp_tools: list[str], result: dict[str, Any]
) -> None:
    oc_dir = Path(worktree) / ".open-code"
    oc_dir.mkdir(exist_ok=True)
    (oc_dir / "instructions.md").write_text(f"""# Agent Instructions (generated by AgentSpec)

{system_prompt}
""")
    result["files_written"].append(".open-code/instructions.md")


def _write_aider_config(
    worktree: str, system_prompt: str, result: dict[str, Any]
) -> None:
    import yaml
    config = {
        "model": "claude-3-5-sonnet-latest",
        "auto-commits": False,
        "yes": True,
    }
    aider_conf = Path(worktree) / ".aider.conf.yml"
    aider_conf.write_text(yaml.dump(config, default_flow_style=False))
    result["files_written"].append(".aider.conf.yml")


# ── YAML export ───────────────────────────────────────────────────────────────


def _save_manifest_yaml(manifest: AgentManifest, path: Path) -> None:
    """Save an AgentManifest as a YAML .agent file."""
    import yaml
    data = manifest.model_dump(exclude_none=True, exclude_defaults=True)
    # Remove internal fields
    data.pop("_source_dir", None)
    data.pop("soul", None)
    data.pop("rules", None)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


# ── Agent Evolution via AgentSpec Inheritance ─────────────────────────────────
#
# After a retro, the evolution engine produces a new .agent file that
# *extends* the previous version. This gives:
#   - Full history: each version is a content-addressed .agent file
#   - Inheritance: child agent inherits parent's config, overrides specific fields
#   - Trust invariant: evolved agent can never escalate permissions
#   - Shareable patterns: evolution rules can be extracted as reusable base agents
#
# Sprint flow:
#   Sprint 1: caloron-agent-impl@1.0.0 (from PO)
#       ↓ retro: low clarity, high failure
#   Sprint 2: caloron-agent-impl@1.1.0 (extends @1.0.0)
#       - behavior: append (add self-review trait)
#       - model: override (stronger model)
#       ↓ retro: clean sprint
#   Sprint 3: caloron-agent-impl@1.1.0 (no change needed)


@dataclass
class EvolutionChange:
    """A single evolution step with AgentSpec mapping."""
    field: str           # retro field: "model", "traits", "instructions", etc.
    old_value: str
    new_value: str
    reason: str
    agentspec_op: str    # what this maps to in .agent: "model.capability", "behavior.traits", etc.


def evolve_agent_manifest(
    base_manifest: AgentManifest,
    retro_data: dict[str, Any],
    performance: dict[str, Any],
    sprint_id: str,
    agents_dir: str | None = None,
) -> tuple[AgentManifest | None, list[EvolutionChange]]:
    """Produce an evolved .agent manifest based on retro findings.

    Applies evolution rules (same logic as agent_versioning.should_evolve)
    but outputs an AgentSpec manifest with inheritance instead of flat patches.

    Returns (evolved_manifest, changes). Returns (None, []) if no evolution needed.
    """
    if not AGENTSPEC_AVAILABLE:
        return None, []

    changes: list[EvolutionChange] = []

    clarity = retro_data.get("avg_clarity", 10)
    failure_rate = retro_data.get("failure_rate", 0)
    interventions = retro_data.get("supervisor_events", 0)
    review_cycles = retro_data.get("avg_review_cycles", 0)
    blockers = retro_data.get("blockers", [])

    # Collect needed modifications
    new_capability = base_manifest.model.capability
    new_traits = list(base_manifest.behavior.traits)
    new_temperature = base_manifest.behavior.temperature
    new_max_steps = base_manifest.behavior.max_steps
    new_preferred = list(base_manifest.model.preferred)
    extra_rules: list[str] = []

    # Rule 1: High failure rate → stronger model
    if failure_rate > 0.3 and base_manifest.model.capability != "reasoning-high":
        old_cap = base_manifest.model.capability
        new_capability = "reasoning-high"
        new_preferred = _framework_preferred_models("claude-code")  # reset to best
        changes.append(EvolutionChange(
            field="model",
            old_value=old_cap,
            new_value="reasoning-high",
            reason=f"Failure rate {failure_rate:.0%} exceeds 30% threshold",
            agentspec_op="model.capability",
        ))

    # Rule 2: Low clarity → add ambiguity-handling trait
    if clarity < 5 and "handle-ambiguity" not in new_traits:
        new_traits.append("handle-ambiguity")
        extra_rules.append(
            "If the task description is unclear, list your assumptions before starting work."
        )
        changes.append(EvolutionChange(
            field="traits",
            old_value="",
            new_value="handle-ambiguity",
            reason=f"Average clarity {clarity}/10 — agent needs ambiguity handling",
            agentspec_op="behavior.traits",
        ))

    # Rule 3: High review cycles → add self-review trait
    if review_cycles > 2 and "self-review" not in new_traits:
        new_traits.append("self-review")
        extra_rules.append(
            "Before submitting, review your code for: missing tests, missing validation, missing type hints."
        )
        changes.append(EvolutionChange(
            field="traits",
            old_value="",
            new_value="self-review",
            reason=f"Average {review_cycles:.1f} review cycles — too many rejections",
            agentspec_op="behavior.traits",
        ))

    # Rule 4: Many supervisor interventions → lower temperature, increase steps
    if interventions > 1:
        if new_temperature > 0.1:
            old_temp = new_temperature
            new_temperature = max(0.1, new_temperature - 0.1)
            changes.append(EvolutionChange(
                field="temperature",
                old_value=str(old_temp),
                new_value=str(new_temperature),
                reason=f"{interventions} supervisor interventions — tighter focus needed",
                agentspec_op="behavior.temperature",
            ))
        if new_max_steps < 80:
            old_steps = new_max_steps
            new_max_steps = min(80, new_max_steps + 10)
            changes.append(EvolutionChange(
                field="max_steps",
                old_value=str(old_steps),
                new_value=str(new_max_steps),
                reason=f"{interventions} interventions — more steps before timeout",
                agentspec_op="behavior.max_steps",
            ))

    # Rule 5: Tool blockers → add missing skills
    new_skills = list(base_manifest.skills)
    for blocker in blockers:
        bl = blocker.lower()
        if "tool" in bl and "unavailable" in bl:
            if "browser" in bl and "browser" not in new_skills:
                new_skills.append("browser")
                changes.append(EvolutionChange(
                    field="skills",
                    old_value="",
                    new_value="browser",
                    reason=f"Blocker: {blocker}",
                    agentspec_op="skills",
                ))
            if "data" in bl and "data-analysis" not in new_skills:
                new_skills.append("data-analysis")
                changes.append(EvolutionChange(
                    field="skills",
                    old_value="",
                    new_value="data-analysis",
                    reason=f"Blocker: {blocker}",
                    agentspec_op="skills",
                ))

    # No changes needed
    if not changes:
        return None, []

    # Build evolved manifest — inherits from base
    version_parts = base_manifest.version.split(".")
    new_minor = int(version_parts[1]) + 1 if len(version_parts) > 1 else 1
    new_version = f"{version_parts[0]}.{new_minor}.0"

    # Build RULES.md content from accumulated rules
    rules_content = base_manifest.rules or ""
    if extra_rules:
        rules_content += "\n\n## Evolution Rules (from retro)\n"
        for rule in extra_rules:
            rules_content += f"- {rule}\n"

    evolved = AgentManifest(
        apiVersion="agent/v1",
        name=base_manifest.name,
        version=new_version,
        description=f"{base_manifest.description} (evolved sprint {sprint_id})",
        tags=base_manifest.tags,
        model=ModelSpec(
            capability=new_capability,
            preferred=new_preferred,
            fallback=base_manifest.model.fallback,
            context=base_manifest.model.context,
        ),
        skills=new_skills,
        tools=base_manifest.tools,
        behavior=BehaviorSpec(
            persona=base_manifest.behavior.persona,
            traits=new_traits,
            temperature=new_temperature,
            max_steps=new_max_steps,
            on_error=base_manifest.behavior.on_error,
            system_override=base_manifest.behavior.system_override,
        ),
        trust=base_manifest.trust,  # never escalate
        observability=base_manifest.observability,
        extensions=base_manifest.extensions,
        rules=rules_content if rules_content.strip() else None,
    )

    # Save evolved .agent file
    if agents_dir:
        Path(agents_dir).mkdir(parents=True, exist_ok=True)
        # Save as versioned file
        safe_name = base_manifest.name.replace("/", "_")
        evolved_file = Path(agents_dir) / f"{safe_name}@{new_version}.agent"
        _save_manifest_yaml(evolved, evolved_file)

        # Also save as "current" (latest) for next sprint to pick up
        current_file = Path(agents_dir) / f"{safe_name}.agent"
        _save_manifest_yaml(evolved, current_file)

    return evolved, changes


def load_previous_manifest(
    agent_id: str, agents_dir: str
) -> AgentManifest | None:
    """Load the most recent .agent file for an agent from the agents directory."""
    if not AGENTSPEC_AVAILABLE:
        return None

    safe_name = f"caloron-agent-{agent_id}"
    current_file = Path(agents_dir) / f"{safe_name}.agent"
    if current_file.exists():
        return load_agent(current_file)
    return None


def auto_evolve_with_agentspec(
    tasks: list[dict[str, Any]],
    retro_data: dict[str, Any],
    feedback_data: list[dict[str, Any]],
    sprint_id: str,
    agents_dir: str,
) -> list[dict[str, Any]]:
    """Run agentspec-based evolution for all agents that ran in this sprint.

    For each agent:
    1. Load its .agent manifest from the agents directory
    2. Check retro data for evolution triggers
    3. If needed, produce an evolved .agent that inherits from the original
    4. Save the evolved .agent for the next sprint

    Returns a list of evolution summaries.
    """
    if not AGENTSPEC_AVAILABLE:
        return []

    evolutions: list[dict[str, Any]] = []

    for task in tasks:
        tid = task.get("id", "")
        manifest = load_previous_manifest(tid, agents_dir)
        if not manifest:
            continue

        # Build per-agent retro data from feedback
        agent_feedback = next((f for f in feedback_data if f.get("task_id") == tid), {})
        per_agent_retro = {
            "avg_clarity": agent_feedback.get("clarity", retro_data.get("avg_clarity", 10)),
            "failure_rate": 0.0 if agent_feedback.get("assessment") == "completed" else 1.0,
            "supervisor_events": retro_data.get("supervisor_events", 0),
            "avg_review_cycles": len(agent_feedback.get("blockers", [])),
            "blockers": agent_feedback.get("blockers", []),
        }
        performance = agent_feedback

        evolved, changes = evolve_agent_manifest(
            manifest, per_agent_retro, performance, sprint_id, agents_dir
        )

        if evolved and changes:
            h = agent_hash(evolved)
            evolutions.append({
                "agent_id": tid,
                "old_version": manifest.version,
                "new_version": evolved.version,
                "hash": h,
                "changes": [
                    {
                        "field": c.field,
                        "old": c.old_value,
                        "new": c.new_value,
                        "reason": c.reason,
                        "agentspec_op": c.agentspec_op,
                    }
                    for c in changes
                ],
            })
            print(f"  Agent {tid}: v{manifest.version} -> v{evolved.version} ({h})")
            for c in changes:
                print(f"    [{c.agentspec_op}] {c.old_value or '(none)'} -> {c.new_value}")
                print(f"      reason: {c.reason}")

    return evolutions


def print_evolution_summary(evolutions: list[dict[str, Any]]) -> None:
    """Print a summary of agent evolution changes."""
    if not evolutions:
        print("  No evolution needed — agents performing well")
        return

    print(f"  {len(evolutions)} agent(s) evolved:")
    for evo in evolutions:
        print(f"    {evo['agent_id']}: v{evo['old_version']} -> v{evo['new_version']} ({evo['hash']})")
        print(f"      {len(evo['changes'])} change(s)")


# ── Print helpers ─────────────────────────────────────────────────────────────


def print_agentspec_assignments(tasks: list[dict[str, Any]]) -> None:
    """Print AgentSpec resolver assignments (similar to hr_agent.print_assignments)."""
    print()
    for t in tasks:
        tid = t.get("id", "?")
        title = t.get("title", "?")
        spec = t.get("agentspec", {})

        if "error" in spec:
            print(f"  {tid}: {title}")
            print(f"    agentspec: FAILED — {spec['error'][:80]}")
            print()
            continue

        runtime = spec.get("runtime", "?")
        model = spec.get("model", "?")
        tools = spec.get("tools", [])
        missing = spec.get("missing_tools", [])
        warnings = spec.get("warnings", [])
        h = spec.get("hash", "?")

        print(f"  {tid}: {title}")
        print(f"    runtime:  {runtime} | model: {model}")
        print(f"    hash:     {h}")
        if tools:
            print(f"    tools:    [{', '.join(tools)}]")
        if missing:
            print(f"    missing:  [{', '.join(missing)}]")
        for w in warnings:
            print(f"    warning:  {w}")
        print()
