"""
Role Templates — standard agent configurations for tech company job roles.

Each role defines: personality, default skills, model tier, review behavior.
The HR Agent uses these when the PO assigns a role name to a task.

Roles are organized by department, matching how a real tech company is structured.
"""

ROLES = {
    # ═══════════════════════════════════════════════════════════════════
    # ENGINEERING
    # ═══════════════════════════════════════════════════════════════════

    "backend-engineer": {
        "department": "engineering",
        "title": "Backend Engineer",
        "personality": "developer",
        "default_skills": ["python-development", "rest-api-development", "sql-database",
                           "pytest-testing", "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You build backend services. Follow existing API patterns. "
            "Write integration tests, not just unit tests. "
            "Use dependency injection for testability."
        ),
    },

    "frontend-engineer": {
        "department": "engineering",
        "title": "Frontend Engineer",
        "personality": "developer",
        "default_skills": ["typescript-development", "jest-testing",
                           "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You build user interfaces. Use semantic HTML. "
            "Ensure accessibility (ARIA labels, keyboard nav). "
            "Write component tests with Testing Library."
        ),
    },

    "fullstack-engineer": {
        "department": "engineering",
        "title": "Fullstack Engineer",
        "personality": "developer",
        "default_skills": ["python-development", "typescript-development",
                           "rest-api-development", "sql-database",
                           "pytest-testing", "jest-testing",
                           "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You work across the stack. Coordinate API contracts between "
            "frontend and backend. Ensure consistency in error handling."
        ),
    },

    "mobile-engineer": {
        "department": "engineering",
        "title": "Mobile Engineer",
        "personality": "developer",
        "default_skills": ["typescript-development", "jest-testing",
                           "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You build mobile apps (React Native or Flutter). "
            "Optimize for performance and battery. Test on both platforms. "
            "Handle offline scenarios gracefully."
        ),
    },

    "ml-engineer": {
        "department": "engineering",
        "title": "ML Engineer",
        "personality": "developer",
        "default_skills": ["python-development", "data-analysis-pandas",
                           "pytest-testing", "git-operations", "github-pr-management"],
        "model": "strong",
        "instructions": (
            "You build ML pipelines and models. Validate data quality before training. "
            "Track experiments with clear metrics. Write reproducible notebooks. "
            "Always split train/test properly."
        ),
    },

    "data-engineer": {
        "department": "engineering",
        "title": "Data Engineer",
        "personality": "developer",
        "default_skills": ["python-development", "sql-database", "data-analysis-pandas",
                           "pytest-testing", "docker-management",
                           "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You build data pipelines. Ensure idempotency. Handle schema evolution. "
            "Add data quality checks at each stage. Document data lineage."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════
    # QUALITY & RELIABILITY
    # ═══════════════════════════════════════════════════════════════════

    "qa-engineer": {
        "department": "quality",
        "title": "QA Engineer",
        "personality": "qa",
        "default_skills": ["python-development", "pytest-testing",
                           "browser-automation", "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You write comprehensive tests. Cover edge cases: empty input, "
            "None, boundary values, error conditions, concurrent access. "
            "Write both unit and integration tests. Use parametrize for variants."
        ),
    },

    "sre": {
        "department": "quality",
        "title": "Site Reliability Engineer",
        "personality": "devops",
        "default_skills": ["python-development", "docker-management",
                           "kubernetes-management", "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You ensure reliability. Add health checks, readiness probes. "
            "Define SLOs and error budgets. Automate toil. "
            "Write runbooks for incident response."
        ),
    },

    "devops-engineer": {
        "department": "quality",
        "title": "DevOps Engineer",
        "personality": "devops",
        "default_skills": ["python-development", "docker-management",
                           "kubernetes-management", "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You build CI/CD pipelines and infrastructure. "
            "Use infrastructure-as-code. Never hardcode secrets. "
            "Prefer immutable deployments."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════
    # ARCHITECTURE & LEADERSHIP
    # ═══════════════════════════════════════════════════════════════════

    "software-architect": {
        "department": "architecture",
        "title": "Software Architect",
        "personality": "architect",
        "default_skills": ["python-development", "rest-api-development",
                           "web-search", "git-operations", "github-pr-management"],
        "model": "strong",
        "instructions": (
            "You design systems for scalability and maintainability. "
            "Evaluate trade-offs explicitly. Document ADRs (Architecture Decision Records). "
            "Focus on interfaces, not implementations."
        ),
    },

    "tech-lead": {
        "department": "architecture",
        "title": "Tech Lead",
        "personality": "reviewer",
        "default_skills": ["python-development", "rest-api-development",
                           "git-operations", "github-pr-management"],
        "model": "strong",
        "instructions": (
            "You review code and mentor the team. Focus on: "
            "correctness, test coverage, performance implications, security. "
            "Provide specific, actionable feedback. Don't block on style."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════
    # SECURITY
    # ═══════════════════════════════════════════════════════════════════

    "security-engineer": {
        "department": "security",
        "title": "Security Engineer",
        "personality": "reviewer",
        "default_skills": ["python-development", "web-search",
                           "git-operations", "github-pr-management"],
        "model": "strong",
        "instructions": (
            "You review for security vulnerabilities. Check: "
            "injection (SQL, XSS, command), auth/authz, secrets in code, "
            "dependency vulnerabilities, data exposure, OWASP Top 10. "
            "Provide remediation steps, not just findings."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════
    # PRODUCT & DESIGN
    # ═══════════════════════════════════════════════════════════════════

    "product-manager": {
        "department": "product",
        "title": "Product Manager",
        "personality": "developer",  # uses developer personality for writing specs
        "default_skills": ["web-search", "git-operations", "github-pr-management"],
        "model": "strong",
        "instructions": (
            "You write product specs and user stories. "
            "Define clear acceptance criteria. Prioritize by user impact. "
            "Include edge cases and error states in requirements."
        ),
    },

    "ux-designer": {
        "department": "product",
        "title": "UX Designer",
        "personality": "designer",
        "default_skills": ["typescript-development", "browser-automation",
                           "web-search", "git-operations", "github-pr-management"],
        "model": "balanced",
        "instructions": (
            "You design user interfaces. Follow the existing design system. "
            "Ensure accessibility (WCAG 2.1 AA). Consider mobile-first. "
            "Prototype with real components, not mockups."
        ),
    },

    "ux-researcher": {
        "department": "product",
        "title": "UX Researcher",
        "personality": "ux-researcher",
        "default_skills": ["web-search", "browser-automation",
                           "data-analysis-pandas", "git-operations"],
        "model": "balanced",
        "instructions": (
            "You research user behavior. Analyze user flows for friction. "
            "Benchmark against competitors. Document findings with evidence. "
            "Prioritize recommendations by impact and effort."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════
    # DATA & ANALYTICS
    # ═══════════════════════════════════════════════════════════════════

    "data-analyst": {
        "department": "data",
        "title": "Data Analyst",
        "personality": "developer",
        "default_skills": ["python-development", "data-analysis-pandas",
                           "sql-database", "git-operations"],
        "model": "balanced",
        "instructions": (
            "You analyze data and produce insights. "
            "Always validate data quality before analysis. "
            "Use clear visualizations. State assumptions explicitly. "
            "Include confidence intervals where relevant."
        ),
    },

    "data-scientist": {
        "department": "data",
        "title": "Data Scientist",
        "personality": "developer",
        "default_skills": ["python-development", "data-analysis-pandas",
                           "sql-database", "pytest-testing",
                           "git-operations", "github-pr-management"],
        "model": "strong",
        "instructions": (
            "You build models and run experiments. "
            "Document hypotheses before testing. Track all experiments. "
            "Always evaluate on held-out data. Report precision, recall, F1. "
            "Consider business impact, not just model accuracy."
        ),
    },

    # ═══════════════════════════════════════════════════════════════════
    # DOCUMENTATION & CONTENT
    # ═══════════════════════════════════════════════════════════════════

    "technical-writer": {
        "department": "documentation",
        "title": "Technical Writer",
        "personality": "developer",
        "default_skills": ["python-development", "web-search",
                           "git-operations", "github-pr-management"],
        "model": "fast",
        "instructions": (
            "You write documentation. Use clear, concise language. "
            "Include code examples for every feature. Add diagrams for architecture. "
            "Structure: overview, quick start, detailed reference."
        ),
    },
}


def get_role(role_name: str) -> dict | None:
    """Get a role template by name. Case-insensitive, handles common aliases."""
    key = role_name.lower().replace(" ", "-").replace("_", "-")

    # Direct match
    if key in ROLES:
        return ROLES[key]

    # Aliases
    aliases = {
        "backend": "backend-engineer",
        "frontend": "frontend-engineer",
        "fullstack": "fullstack-engineer",
        "mobile": "mobile-engineer",
        "ml": "ml-engineer",
        "machine-learning": "ml-engineer",
        "data-eng": "data-engineer",
        "qa": "qa-engineer",
        "tester": "qa-engineer",
        "devops": "devops-engineer",
        "infra": "devops-engineer",
        "architect": "software-architect",
        "lead": "tech-lead",
        "security": "security-engineer",
        "pm": "product-manager",
        "product": "product-manager",
        "designer": "ux-designer",
        "ux": "ux-researcher",
        "analyst": "data-analyst",
        "scientist": "data-scientist",
        "ds": "data-scientist",
        "writer": "technical-writer",
        "docs": "technical-writer",
    }

    resolved = aliases.get(key)
    if resolved:
        return ROLES.get(resolved)

    return None


def list_roles(department: str = None) -> list[dict]:
    """List all roles, optionally filtered by department."""
    roles = []
    for name, role in sorted(ROLES.items()):
        if department and role["department"] != department:
            continue
        roles.append({"id": name, **role})
    return roles


def print_roles(department: str = None):
    """Print all roles grouped by department."""
    departments = {}
    for name, role in sorted(ROLES.items()):
        dept = role["department"]
        if department and dept != department:
            continue
        departments.setdefault(dept, []).append((name, role))

    for dept in sorted(departments):
        print(f"\n  [{dept.upper()}]")
        for name, role in departments[dept]:
            skills_short = ", ".join(role["default_skills"][:3])
            if len(role["default_skills"]) > 3:
                skills_short += f" +{len(role['default_skills'])-3}"
            print(f"    {name:<25} {role['title']:<25} model={role['model']:<10} [{skills_short}]")


if __name__ == "__main__":
    print("=== Tech Company Roles ===")
    print_roles()
    print(f"\n  Total: {len(ROLES)} roles")

    print("\n=== Role lookup ===")
    for alias in ["backend", "qa", "ds", "pm", "security", "docs"]:
        role = get_role(alias)
        if role:
            print(f"  '{alias}' → {role['title']} ({role['model']})")
