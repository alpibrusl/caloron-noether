"""
Agent Configurator — translates HR Agent skill assignments into
framework-specific configuration files.

For each agent, generates:
- Claude Code: --mcp-config JSON + CLAUDE.md with skill instructions
- Cursor CLI: .cursorrules + MCP config
- Gemini CLI: system instruction file
- Aider: .aider.conf.yml

These files are written to the agent's worktree before it runs.
"""
import json
import os
from pathlib import Path


def install_dependencies(worktree: str, deps: dict):
    """Install skill dependencies into the worktree environment.

    Handles: pip packages, npm packages, setup commands.
    Nix packages are handled by the Nix flake generator (not here).
    """
    import subprocess

    pip_pkgs = deps.get("pip", [])
    npm_pkgs = deps.get("npm", [])
    setup_cmds = deps.get("setup", [])

    if pip_pkgs:
        # Write requirements.txt for pip packages
        req_path = os.path.join(worktree, "requirements-skills.txt")
        existing = set()
        if os.path.exists(req_path):
            existing = set(Path(req_path).read_text().strip().split("\n"))
        all_pkgs = sorted(existing | set(pip_pkgs))
        Path(req_path).write_text("\n".join(all_pkgs) + "\n")

        # Install (best effort — may fail in sandbox)
        try:
            subprocess.run(
                ["pip", "install", "--quiet", "--user"] + pip_pkgs,
                cwd=worktree, capture_output=True, timeout=60)
        except Exception:
            pass  # Agent can install from requirements-skills.txt

    if npm_pkgs:
        # Add to package.json devDependencies if it exists
        pkg_path = os.path.join(worktree, "package.json")
        if os.path.exists(pkg_path):
            try:
                pkg = json.loads(Path(pkg_path).read_text())
                dev_deps = pkg.setdefault("devDependencies", {})
                for npm_pkg in npm_pkgs:
                    if npm_pkg not in dev_deps:
                        dev_deps[npm_pkg] = "*"
                Path(pkg_path).write_text(json.dumps(pkg, indent=2))
            except Exception:
                pass

    if setup_cmds:
        # Write setup commands to a script the agent can run
        setup_path = os.path.join(worktree, "setup-skills.sh")
        lines = ["#!/bin/bash", "# Auto-generated: install skill dependencies"]
        lines.extend(setup_cmds)
        Path(setup_path).write_text("\n".join(lines) + "\n")
        os.chmod(setup_path, 0o755)

        # Try running setup (best effort)
        for cmd in setup_cmds:
            try:
                subprocess.run(
                    cmd.split(), cwd=worktree,
                    capture_output=True, timeout=120)
            except Exception:
                pass


def _run_quiet(cmd: list[str], cwd: str = None, timeout: int = 15):
    """Run a command quietly, swallowing errors."""
    import subprocess
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
    except Exception:
        pass


# ── Claude Code: claude mcp add ────────────────────────────────────────────

def _claude_mcp_add(name: str, command: str, args: list[str], worktree: str,
                    env: dict = None, scope: str = "project"):
    """Register an MCP server via `claude mcp add`."""
    cmd = ["claude", "mcp", "add", f"--scope={scope}"]
    if env:
        for k, v in env.items():
            cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([name, "--", command] + args)
    _run_quiet(cmd, cwd=worktree)


def _claude_mcp_add_http(name: str, url: str, worktree: str,
                         headers: dict = None, scope: str = "project"):
    """Register an HTTP MCP server via `claude mcp add --transport http`."""
    cmd = ["claude", "mcp", "add", f"--scope={scope}", "--transport", "http"]
    if headers:
        for k, v in headers.items():
            cmd.extend(["--header", f"{k}: {v}"])
    cmd.extend([name, url])
    _run_quiet(cmd, cwd=worktree)


# ── Codex CLI: codex mcp add ───────────────────────────────────────────────

def _codex_mcp_add(name: str, command: str, args: list[str], worktree: str,
                   env: dict = None):
    """Register an MCP server via `codex mcp add name -- cmd args`."""
    cmd = ["codex", "mcp", "add"]
    if env:
        for k, v in env.items():
            cmd.extend(["--env", f"{k}={v}"])
    cmd.extend([name, "--", command] + args)
    _run_quiet(cmd, cwd=worktree)


def _codex_mcp_add_http(name: str, url: str, worktree: str,
                        bearer_env: str = None):
    """Register an HTTP MCP server via `codex mcp add --url`."""
    cmd = ["codex", "mcp", "add", name, "--url", url]
    if bearer_env:
        cmd.extend(["--bearer-token-env-var", bearer_env])
    _run_quiet(cmd, cwd=worktree)


# ── Cursor: cursor --add-mcp ───────────────────────────────────────────────

def _cursor_mcp_add(name: str, command: str, args: list[str], worktree: str,
                    env: dict = None):
    """Register an MCP server via `cursor --add-mcp '{json}'`."""
    mcp_def = {"name": name, "command": command, "args": args}
    if env:
        mcp_def["env"] = env
    cmd = ["cursor", "--add-mcp", json.dumps(mcp_def), "--mcp-workspace", worktree]
    _run_quiet(cmd, cwd=worktree)


def _cursor_mcp_add_http(name: str, url: str, worktree: str):
    """Register an HTTP MCP server via Cursor."""
    mcp_def = {"name": name, "url": url}
    cmd = ["cursor", "--add-mcp", json.dumps(mcp_def), "--mcp-workspace", worktree]
    _run_quiet(cmd, cwd=worktree)


# ── Framework-agnostic MCP registration ────────────────────────────────────

def register_mcp(framework: str, name: str, url: str, worktree: str,
                 env: dict = None):
    """Register an MCP server using the framework's native CLI.

    Falls back to writing config files if CLI is not available.
    """
    if url.startswith("http://") or url.startswith("https://"):
        # HTTP MCP server
        if framework == "claude-code":
            _claude_mcp_add_http(name, url, worktree)
        elif framework == "codex-cli":
            _codex_mcp_add_http(name, url, worktree)
        elif framework == "cursor-cli":
            _cursor_mcp_add_http(name, url, worktree)
        # gemini-cli, open-code, aider: config file only (no CLI for MCP)
    else:
        # stdio MCP server (npx, docker, etc.)
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            command = "npx"
            args = ["-y", "@modelcontextprotocol/server-postgres", url]
        elif url.startswith("slack://"):
            command = "npx"
            args = ["-y", "@anthropic-ai/mcp-slack"]
        else:
            command = "npx"
            args = ["-y", "mcp-remote", url]

        if framework == "claude-code":
            _claude_mcp_add(name, command, args, worktree, env=env)
        elif framework == "codex-cli":
            _codex_mcp_add(name, command, args, worktree, env=env)
        elif framework == "cursor-cli":
            _cursor_mcp_add(name, command, args, worktree, env=env)


def configure_agent(
    worktree: str,
    task: dict,
    framework: str = "claude-code",
) -> dict:
    """Configure the agent's worktree with skill-specific files and install dependencies.

    Returns a dict with any extra CLI flags to pass to the framework.
    """
    skills = task.get("skills", [])
    mcp_urls = task.get("mcp_urls", [])
    model = task.get("model", "balanced")
    deps = task.get("dependencies", {})

    extra_flags = []

    # Install dependencies from skills
    install_dependencies(worktree, deps)

    if framework == "claude-code":
        extra_flags = configure_claude_code(worktree, task, skills, mcp_urls)
    elif framework == "cursor-cli":
        configure_cursor(worktree, task, skills, mcp_urls)
    elif framework == "gemini-cli":
        configure_gemini(worktree, task, skills, mcp_urls)
    elif framework == "codex-cli":
        configure_codex(worktree, task, skills, mcp_urls)
    elif framework == "open-code":
        configure_open_code(worktree, task, skills, mcp_urls)
    elif framework == "aider":
        configure_aider(worktree, task, skills)

    return {"extra_flags": extra_flags}


def configure_claude_code(
    worktree: str,
    task: dict,
    skills: list[str],
    mcp_urls: list[dict],
) -> list[str]:
    """Configure Claude Code with MCP servers, plugins, and CLAUDE.md.

    Two approaches for MCP setup:
    1. `claude mcp add` — registers MCPs via CLI (persistent, preferred)
    2. `.mcp.json` file — loaded via --mcp-config flag (fallback)

    Both are generated so agents work whether claude CLI is available or not.
    """
    import subprocess
    extra_flags = []

    if mcp_urls:
        mcp_config = {"mcpServers": {}}

        for mcp in mcp_urls:
            name = mcp["name"]
            url = mcp["url"]
            env = {}

            if url.startswith("postgresql://") or url.startswith("postgres://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres", url],
                }
            elif url.startswith("http://") or url.startswith("https://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "mcp-remote", url],
                }
            elif url.startswith("slack://"):
                env = {"SLACK_TOKEN": os.environ.get("SLACK_TOKEN", "")}
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "@anthropic-ai/mcp-slack"],
                    "env": {"SLACK_TOKEN": "${SLACK_TOKEN}"},
                }

            # Register via native CLI (claude mcp add)
            register_mcp("claude-code", name, url, worktree, env=env or None)

        # Write .mcp.json as fallback
        config_path = os.path.join(worktree, ".mcp.json")
        Path(config_path).write_text(json.dumps(mcp_config, indent=2))
        extra_flags.extend(["--mcp-config", config_path])

    # ── CLAUDE.md — skill-specific instructions ─────────────────────────
    claude_md_lines = ["# Agent Configuration", ""]
    claude_md_lines.append(f"Task: {task.get('title', '')}")
    claude_md_lines.append(f"Skills: {', '.join(skills)}")
    claude_md_lines.append("")

    for skill_name in skills:
        instructions = SKILL_INSTRUCTIONS.get(skill_name)
        if instructions:
            claude_md_lines.append(f"## {skill_name}")
            claude_md_lines.append(instructions)
            claude_md_lines.append("")

    claude_md_path = os.path.join(worktree, "CLAUDE.md")
    Path(claude_md_path).write_text("\n".join(claude_md_lines))

    return extra_flags


def configure_cursor(
    worktree: str,
    task: dict,
    skills: list[str],
    mcp_urls: list[dict],
):
    """Configure Cursor CLI with .cursorrules and MCP config."""
    # ── .cursorrules ────────────────────────────────────────────────────
    rules_lines = []
    rules_lines.append(f"# Task: {task.get('title', '')}")
    rules_lines.append(f"# Skills: {', '.join(skills)}")
    rules_lines.append("")

    for skill_name in skills:
        instructions = SKILL_INSTRUCTIONS.get(skill_name)
        if instructions:
            rules_lines.append(f"# {skill_name}")
            rules_lines.append(instructions)
            rules_lines.append("")

    Path(os.path.join(worktree, ".cursorrules")).write_text("\n".join(rules_lines))

    # ── MCP config for Cursor ───────────────────────────────────────────
    if mcp_urls:
        mcp_config = {"mcpServers": {}}
        for mcp in mcp_urls:
            mcp_config["mcpServers"][mcp["name"]] = {"url": mcp["url"]}
            # Register via native CLI: cursor --add-mcp
            register_mcp("cursor-cli", mcp["name"], mcp["url"], worktree)

        # Write config file as fallback
        Path(os.path.join(worktree, ".cursor", "mcp.json")).parent.mkdir(parents=True, exist_ok=True)
        Path(os.path.join(worktree, ".cursor", "mcp.json")).write_text(
            json.dumps(mcp_config, indent=2))


def configure_gemini(
    worktree: str,
    task: dict,
    skills: list[str],
    mcp_urls: list[dict],
):
    """Configure Gemini CLI with GEMINI.md and MCP settings.

    Gemini CLI reads:
    - GEMINI.md (like CLAUDE.md — system instructions)
    - .gemini/settings.json for MCP servers
    """
    # ── GEMINI.md — skill instructions ──────────────────────────────────
    lines = ["# Agent Configuration", ""]
    lines.append(f"Task: {task.get('title', '')}")
    lines.append(f"Skills: {', '.join(skills)}")
    lines.append("")

    for skill_name in skills:
        inst = SKILL_INSTRUCTIONS.get(skill_name)
        if inst:
            lines.append(f"## {skill_name}")
            lines.append(inst)
            lines.append("")

    Path(os.path.join(worktree, "GEMINI.md")).write_text("\n".join(lines))

    # ── MCP config for Gemini ───────────────────────────────────────────
    if mcp_urls:
        gemini_dir = os.path.join(worktree, ".gemini")
        os.makedirs(gemini_dir, exist_ok=True)
        mcp_config = {"mcpServers": {}}
        for mcp in mcp_urls:
            name = mcp["name"]
            url = mcp["url"]
            if url.startswith("http://") or url.startswith("https://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "mcp-remote", url],
                }
            elif url.startswith("postgresql://") or url.startswith("postgres://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres", url],
                }
        Path(os.path.join(gemini_dir, "settings.json")).write_text(
            json.dumps(mcp_config, indent=2))


def configure_codex(
    worktree: str,
    task: dict,
    skills: list[str],
    mcp_urls: list[dict],
):
    """Configure OpenAI Codex CLI.

    Codex CLI reads:
    - AGENTS.md (system instructions, like CLAUDE.md)
    - codex.json for MCP servers
    """
    # ── AGENTS.md ───────────────────────────────────────────────────────
    lines = ["# Agent Configuration", ""]
    lines.append(f"Task: {task.get('title', '')}")
    lines.append(f"Skills: {', '.join(skills)}")
    lines.append("")

    for skill_name in skills:
        inst = SKILL_INSTRUCTIONS.get(skill_name)
        if inst:
            lines.append(f"## {skill_name}")
            lines.append(inst)
            lines.append("")

    Path(os.path.join(worktree, "AGENTS.md")).write_text("\n".join(lines))

    # ── MCP config ──────────────────────────────────────────────────────
    if mcp_urls:
        mcp_config = {"mcpServers": {}}
        for mcp in mcp_urls:
            name = mcp["name"]
            url = mcp["url"]
            if url.startswith("http://") or url.startswith("https://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "mcp-remote", url],
                }
            elif url.startswith("postgresql://") or url.startswith("postgres://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres", url],
                }
            # Register via native CLI: codex mcp add
            register_mcp("codex-cli", name, url, worktree)

        # Write config file as fallback
        Path(os.path.join(worktree, "codex.json")).write_text(
            json.dumps(mcp_config, indent=2))


def configure_open_code(
    worktree: str,
    task: dict,
    skills: list[str],
    mcp_urls: list[dict],
):
    """Configure open-code (open-source VS Code CLI agent).

    open-code reads:
    - .open-code/instructions.md for system instructions
    - .open-code/mcp.json for MCP servers
    """
    oc_dir = os.path.join(worktree, ".open-code")
    os.makedirs(oc_dir, exist_ok=True)

    # ── Instructions ────────────────────────────────────────────────────
    lines = ["# Agent Configuration", ""]
    lines.append(f"Task: {task.get('title', '')}")
    lines.append(f"Skills: {', '.join(skills)}")
    lines.append("")

    for skill_name in skills:
        inst = SKILL_INSTRUCTIONS.get(skill_name)
        if inst:
            lines.append(f"## {skill_name}")
            lines.append(inst)
            lines.append("")

    Path(os.path.join(oc_dir, "instructions.md")).write_text("\n".join(lines))

    # ── MCP config ──────────────────────────────────────────────────────
    if mcp_urls:
        mcp_config = {"mcpServers": {}}
        for mcp in mcp_urls:
            name = mcp["name"]
            url = mcp["url"]
            if url.startswith("http://") or url.startswith("https://"):
                mcp_config["mcpServers"][name] = {"url": url}
            elif url.startswith("postgresql://") or url.startswith("postgres://"):
                mcp_config["mcpServers"][name] = {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-postgres", url],
                }
        Path(os.path.join(oc_dir, "mcp.json")).write_text(
            json.dumps(mcp_config, indent=2))


def configure_aider(
    worktree: str,
    task: dict,
    skills: list[str],
):
    """Configure Aider with .aider.conf.yml."""
    config = {
        "auto-commits": False,
        "yes": True,
    }

    conventions = []
    for skill_name in skills:
        inst = SKILL_INSTRUCTIONS.get(skill_name)
        if inst:
            conventions.append(inst)

    if conventions:
        config["conventions"] = "\n".join(conventions)

    try:
        import yaml
        Path(os.path.join(worktree, ".aider.conf.yml")).write_text(
            yaml.dump(config, default_flow_style=False))
    except ImportError:
        Path(os.path.join(worktree, ".aider.conf.json")).write_text(
            json.dumps(config, indent=2))


# ── Skill-specific instructions per framework ──────────────────────────────

SKILL_INSTRUCTIONS = {
    "python-development": (
        "Use Python 3.11+. Always add type hints to function signatures. "
        "Use pathlib for file operations. Prefer dataclasses over plain dicts for structured data."
    ),
    "rust-development": (
        "Use idiomatic Rust. Prefer Result<T, E> over panics. "
        "Run cargo fmt and cargo clippy before committing."
    ),
    "typescript-development": (
        "Use strict TypeScript. Define interfaces for all data structures. "
        "Use async/await, not callbacks."
    ),
    "pytest-testing": (
        "Use pytest with parametrize for multiple test cases. "
        "Test edge cases: empty input, None, boundary values, error conditions. "
        "Use fixtures for shared setup. Aim for >80% coverage."
    ),
    "jest-testing": (
        "Use Jest with describe/it blocks. Mock external dependencies. "
        "Test both success and error paths."
    ),
    "data-analysis-pandas": (
        "Use pandas for data loading and transformation. "
        "Always validate DataFrame columns before processing. "
        "Handle missing values explicitly (don't silently drop). "
        "Use .copy() when modifying DataFrames to avoid SettingWithCopyWarning."
    ),
    "sql-database": (
        "Use parameterized queries (never f-strings for SQL). "
        "Always close connections/cursors. Use connection pooling for web services. "
        "Add database migrations for schema changes."
    ),
    "rest-api-development": (
        "Use FastAPI with Pydantic models for request/response validation. "
        "Add OpenAPI documentation. Return proper HTTP status codes. "
        "Add health check endpoint at GET /health."
    ),
    "docker-management": (
        "Use multi-stage builds. Pin base image versions. "
        "Don't run as root. Use .dockerignore."
    ),
    "kubernetes-management": (
        "Define resource requests and limits. Use readiness/liveness probes. "
        "Use ConfigMaps for config, Secrets for credentials."
    ),
    "ota-pricing-analysis": (
        "When analyzing hotel rates, consider seasonality (weekday vs weekend, "
        "holiday periods). Use rolling windows for baseline calculation. "
        "Z-score threshold of 2.0 is standard; flag but don't auto-correct."
    ),
    "charging-optimization": (
        "Validate SoC bounds (0-100%). Cap charging at battery capacity. "
        "Consider charger power limits. Handle impossible constraints gracefully "
        "(raise ValueError with clear message, don't silently return bad results)."
    ),
    "github-pr-management": (
        "Create PRs with clear descriptions linking to the issue. "
        "Use conventional commit messages. Keep PRs focused on one change."
    ),
    "git-operations": (
        "Commit frequently with descriptive messages. "
        "Don't commit generated files or secrets."
    ),
    "web-search": (
        "Search for documentation and examples before implementing. "
        "Cite sources when using external patterns."
    ),
    "noether-compose": (
        "Use Noether stages for any computation that could be reused. "
        "Search existing stages before creating new ones."
    ),
}


def print_config_summary(worktree: str, framework: str):
    """Show what config files were generated."""
    configs = {
        "CLAUDE.md": os.path.exists(os.path.join(worktree, "CLAUDE.md")),
        ".mcp.json": os.path.exists(os.path.join(worktree, ".mcp.json")),
        ".cursorrules": os.path.exists(os.path.join(worktree, ".cursorrules")),
        ".cursor/mcp.json": os.path.exists(os.path.join(worktree, ".cursor", "mcp.json")),
        "GEMINI.md": os.path.exists(os.path.join(worktree, "GEMINI.md")),
        ".gemini/settings.json": os.path.exists(os.path.join(worktree, ".gemini", "settings.json")),
        "AGENTS.md": os.path.exists(os.path.join(worktree, "AGENTS.md")),
        "codex.json": os.path.exists(os.path.join(worktree, "codex.json")),
        ".open-code/instructions.md": os.path.exists(os.path.join(worktree, ".open-code", "instructions.md")),
        ".open-code/mcp.json": os.path.exists(os.path.join(worktree, ".open-code", "mcp.json")),
        ".aider.conf.yml": os.path.exists(os.path.join(worktree, ".aider.conf.yml")),
    }
    generated = [k for k, v in configs.items() if v]
    if generated:
        print(f"    config: [{', '.join(generated)}]")


# ── Self-test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as worktree:
        task = {
            "id": "api-task",
            "title": "Build FastAPI endpoint with PostgreSQL",
            "skills": ["rest-api-development", "sql-database", "pytest-testing", "github-pr-management"],
            "mcp_urls": [
                {"name": "sql-database", "url": "postgresql://localhost:5432/mydb"},
                {"name": "github-pr-management", "url": "https://github.mcp.claude.com/mcp"},
            ],
            "model": "balanced",
        }

        print("=== Claude Code Configuration ===")
        result = configure_agent(worktree, task, "claude-code")
        print(f"  Extra flags: {result['extra_flags']}")
        print()

        print("--- CLAUDE.md ---")
        print(Path(os.path.join(worktree, "CLAUDE.md")).read_text())

        print("--- .mcp.json ---")
        print(Path(os.path.join(worktree, ".mcp.json")).read_text())

        print()
        print("=== Cursor Configuration ===")
        configure_agent(worktree, task, "cursor-cli")
        print("--- .cursorrules ---")
        print(Path(os.path.join(worktree, ".cursorrules")).read_text()[:300])
