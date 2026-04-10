"""
Post-Sprint Deploy — build and run what agents built.

After a sprint completes:
1. Detect project type from generated files
2. Run tests
3. Build (Docker or direct)
4. Run and show output
5. For web apps: show the URL
6. For CLIs: show the help/usage

This is the open-source version — runs locally.
The enterprise version (noether-cloud/agents/deploy) adds:
- Preview URLs, mobile distribution, production quality gates.
"""
import json
import os
import subprocess
from pathlib import Path


def detect_project_type(project_dir: str) -> dict:
    """Detect what kind of project was built."""
    files = set()
    for root, dirs, fnames in os.walk(project_dir):
        for f in fnames:
            rel = os.path.relpath(os.path.join(root, f), project_dir)
            if not rel.startswith(".git/"):
                files.add(rel)

    result = {
        "type": "unknown",
        "language": "unknown",
        "has_tests": False,
        "has_dockerfile": False,
        "has_ci": False,
        "runnable": False,
        "run_command": None,
        "test_command": None,
    }

    # Detect language and framework
    if "pyproject.toml" in files or "setup.py" in files:
        result["language"] = "python"
        result["test_command"] = "python3 -m pytest tests/ -v"

        if any("fastapi" in (Path(project_dir) / "pyproject.toml").read_text().lower()
               for _ in [1] if (Path(project_dir) / "pyproject.toml").exists()):
            result["type"] = "web-api"
            result["run_command"] = "uvicorn src.main:app --host 0.0.0.0 --port 8000"
            result["runnable"] = True
        elif any("argparse" in (Path(project_dir) / f).read_text()
                 for f in files if f.startswith("src/") and f.endswith(".py")
                 and (Path(project_dir) / f).exists()):
            result["type"] = "cli"
            result["runnable"] = True
        else:
            result["type"] = "library"

    elif "package.json" in files:
        result["language"] = "typescript"
        pkg = json.loads((Path(project_dir) / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

        if "next" in deps:
            result["type"] = "web-app"
            result["run_command"] = "npm run dev"
            result["test_command"] = "npm test"
            result["runnable"] = True
        elif "react-native" in deps or "expo" in deps:
            result["type"] = "mobile"
            result["test_command"] = "npm test"
        elif "express" in deps:
            result["type"] = "web-api"
            result["run_command"] = "npm start"
            result["test_command"] = "npm test"
            result["runnable"] = True

    elif "Cargo.toml" in files:
        result["language"] = "rust"
        result["type"] = "cli"
        result["run_command"] = "cargo run"
        result["test_command"] = "cargo test"
        result["runnable"] = True

    # Check for tests, docker, CI
    result["has_tests"] = any(f.startswith("tests/") and f.endswith(".py") for f in files) or \
                          any("test" in f.lower() for f in files if f.endswith(".ts") or f.endswith(".js"))
    result["has_dockerfile"] = "Dockerfile" in files
    result["has_ci"] = ".github/workflows/ci.yml" in files

    return result


def run_tests(project_dir: str, test_command: str) -> dict:
    """Run the project's tests and return results."""
    try:
        result = subprocess.run(
            test_command.split(),
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        passed = result.returncode == 0
        return {
            "passed": passed,
            "output": result.stdout[-500:] if result.stdout else "",
            "errors": result.stderr[-300:] if result.stderr else "",
        }
    except Exception as e:
        return {"passed": False, "output": "", "errors": str(e)}


def build_docker(project_dir: str, tag: str = "sprint-latest") -> dict:
    """Build a Docker image from the project."""
    try:
        result = subprocess.run(
            ["docker", "build", "-t", tag, "."],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "success": result.returncode == 0,
            "tag": tag,
            "errors": result.stderr[-300:] if result.returncode != 0 else "",
        }
    except Exception as e:
        return {"success": False, "tag": tag, "errors": str(e)}


def run_project(project_dir: str, run_command: str, timeout: int = 5) -> dict:
    """Start the project and capture initial output."""
    try:
        result = subprocess.run(
            run_command.split(),
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"output": result.stdout[:500], "errors": result.stderr[:300]}
    except subprocess.TimeoutExpired:
        return {"output": "(server started — still running)", "errors": ""}
    except Exception as e:
        return {"output": "", "errors": str(e)}


def post_sprint_deploy(project_dir: str, sprint_id: str = "latest") -> dict:
    """Full post-sprint deployment: detect → test → build → run."""
    results = {"sprint_id": sprint_id, "steps": []}

    # Step 1: Detect
    project = detect_project_type(project_dir)
    results["project"] = project
    results["steps"].append(f"Detected: {project['type']} ({project['language']})")

    # Step 2: Test
    if project["has_tests"] and project.get("test_command"):
        test_result = run_tests(project_dir, project["test_command"])
        results["tests"] = test_result
        if test_result["passed"]:
            results["steps"].append("Tests: PASSED")
        else:
            results["steps"].append("Tests: FAILED")
            results["deploy_blocked"] = "Tests failed"
            return results

    # Step 3: Build (if Dockerfile exists)
    if project["has_dockerfile"]:
        tag = f"caloron-sprint-{sprint_id}"
        build_result = build_docker(project_dir, tag)
        results["build"] = build_result
        if build_result["success"]:
            results["steps"].append(f"Docker build: {tag}")
        else:
            results["steps"].append("Docker build: FAILED")

    # Step 4: Show what was built
    if project["type"] == "cli" and project.get("run_command"):
        # For CLIs, show --help
        help_cmd = project["run_command"].replace("cargo run", "cargo run -- --help")
        if "python" in project["language"]:
            help_cmd = "python3 -m src.cli --help"
        run_result = run_project(project_dir, help_cmd, timeout=10)
        results["preview"] = run_result
        results["steps"].append("CLI help output captured")

    elif project["type"] in ("web-api", "web-app") and project.get("run_command"):
        results["steps"].append(f"Run with: {project['run_command']}")
        if project["has_dockerfile"]:
            results["steps"].append(f"Or: docker run -p 8000:8000 caloron-sprint-{sprint_id}")

    return results


def print_deploy_summary(results: dict):
    """Print a human-readable deployment summary."""
    BOLD, GREEN, YELLOW, RED, RESET = '\033[1m', '\033[32m', '\033[33m', '\033[31m', '\033[0m'

    print(f"\n{BOLD}Post-Sprint Deployment{RESET}")
    print()

    project = results.get("project", {})
    print(f"  Project: {project.get('type', '?')} ({project.get('language', '?')})")
    print(f"  Tests: {'yes' if project.get('has_tests') else 'no'}")
    print(f"  Dockerfile: {'yes' if project.get('has_dockerfile') else 'no'}")
    print(f"  CI: {'yes' if project.get('has_ci') else 'no'}")
    print()

    for step in results.get("steps", []):
        icon = GREEN + "✓" if "PASSED" in step or "Detected" in step or "captured" in step else \
               RED + "✗" if "FAILED" in step else YELLOW + "→"
        print(f"  {icon}{RESET} {step}")

    if results.get("preview", {}).get("output"):
        print(f"\n  {BOLD}Preview:{RESET}")
        for line in results["preview"]["output"].split("\n")[:10]:
            print(f"    {line}")

    if results.get("deploy_blocked"):
        print(f"\n  {RED}Deployment blocked: {results['deploy_blocked']}{RESET}")
    else:
        print(f"\n  {GREEN}Ready for review{RESET}")

    print()


if __name__ == "__main__":
    import sys
    project_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    results = post_sprint_deploy(project_dir)
    print_deploy_summary(results)
