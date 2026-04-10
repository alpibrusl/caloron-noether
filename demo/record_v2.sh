#!/bin/bash
# ==========================================================================
# Caloron v2 Demo — Full Pipeline
#
# Shows: PO → Roles → HR Agent → Skills → Template → Agents → Review → Deploy
# ==========================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CALORON_DIR="$(dirname "$SCRIPT_DIR")"
ORCH_DIR="$CALORON_DIR/orchestrator"

BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
CYAN='\033[36m'
RESET='\033[0m'

narrate() { echo -e "\n${BOLD}${CYAN}▸ $1${RESET}"; sleep 1; }
ok() { echo -e "  ${GREEN}✓${RESET} $1"; }
type_cmd() { echo -ne "\n${DIM}\$ ${RESET}"; for ((i=0; i<${#1}; i++)); do echo -n "${1:$i:1}"; sleep 0.02; done; echo; sleep 0.3; }

clear
echo ""
echo -e "${BOLD}  ╔═══════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}  ║  ${CYAN}CALORON${RESET}${BOLD} — Multi-Agent Sprint with Roles & Skills  ║${RESET}"
echo -e "${BOLD}  ╚═══════════════════════════════════════════════════╝${RESET}"
echo ""
sleep 2

# ── Show available roles ────────────────────────────────────────────────
narrate "Available roles in the system"
type_cmd "python3 -c 'from roles import print_roles; print_roles()'"
cd "$ORCH_DIR"
python3 -c "from roles import print_roles; print_roles()" 2>/dev/null | head -25
sleep 2

# ── Show skill store ────────────────────────────────────────────────────
narrate "Skill store with dependency chains"
type_cmd "python3 -c 'from skill_store import SkillStore, print_store; print_store(SkillStore(\"/tmp/demo_skills.json\"))'"
python3 -c "
from skill_store import SkillStore
store = SkillStore('/tmp/demo_skills.json')
# Show a few interesting skills
for name in ['browser-automation', 'rest-api-development', 'sql-database', 'data-analysis-pandas']:
    s = store.get(name)
    if s:
        print(f'  {name}:')
        print(f'    nix: {s.nix_packages}')
        print(f'    pip: {s.pip_packages}')
        if s.setup_commands: print(f'    setup: {s.setup_commands}')
        if s.mcp_url: print(f'    mcp: {s.mcp_url}')
        print()
" 2>/dev/null
sleep 2

# ── HR Agent demo ───────────────────────────────────────────────────────
narrate "HR Agent assigns skills to tasks"
type_cmd "python3 hr_agent.py"
python3 -c "
from skill_store import SkillStore
from hr_agent import analyze_task_skills
import json

store = SkillStore('/tmp/demo_skills.json')

tasks = [
    {'id': 'api', 'title': 'Build FastAPI hotel rate endpoint with PostgreSQL',
     'agent_prompt': 'Create REST API with database connection'},
    {'id': 'scraper', 'title': 'Scrape competitor hotel prices with playwright',
     'agent_prompt': 'Use playwright to take screenshots and extract prices'},
    {'id': 'tests', 'title': 'Write pytest tests for all modules',
     'agent_prompt': 'Comprehensive tests with fixtures and parametrize'},
]

for task in tasks:
    result = analyze_task_skills(task, store)
    print(f'  {result[\"id\"]}: {result[\"title\"][:50]}')
    print(f'    role: {result[\"model\"]} | skills: {result[\"skills\"][:4]}')
    deps = result.get('dependencies', {})
    if deps.get('pip'): print(f'    pip: {deps[\"pip\"]}')
    if deps.get('setup'): print(f'    setup: {deps[\"setup\"]}')
    print()
" 2>/dev/null
sleep 2

# ── Template matching ───────────────────────────────────────────────────
narrate "Template store matches project scaffolds"
type_cmd "ls templates/"
ls "$CALORON_DIR/templates/"
sleep 1

type_cmd "python3 -c '...match fastapi-postgres...'"
python3 -c "
from template_store import match_template, TEMPLATES, load_yaml_templates
all_t = {**TEMPLATES, **load_yaml_templates('$CALORON_DIR/templates')}
for skills, text in [
    (['rest-api-development', 'sql-database'], 'FastAPI with PostgreSQL'),
    (['data-analysis-pandas'], 'analyze CSV data'),
    (['typescript-development'], 'Next.js web app'),
    (['python-development'], 'CLI calculator'),
]:
    # Try yaml templates first
    best = None
    best_score = 0
    for tid, t in all_t.items():
        score = sum(2 for s in t.get('match_skills',[]) if s in skills) + sum(1 for k in t.get('match_keywords',[]) if k in text.lower())
        if score > best_score:
            best_score = score
            best = tid
    name = all_t[best]['name'] if best and best_score >= 2 else '(no match)'
    print(f'  [{skills[0][:20]}] \"{text}\" → {name}')
" 2>/dev/null
sleep 2

# ── Agent configurator ─────────────────────────────────────────────────
narrate "Agent configurator generates framework-specific files"
type_cmd "python3 agent_configurator.py"
python3 -c "
import tempfile, os
from agent_configurator import configure_agent

task = {
    'title': 'Build API with PostgreSQL',
    'skills': ['rest-api-development', 'sql-database'],
    'mcp_urls': [{'name': 'postgres', 'url': 'postgresql://localhost/db'}],
    'dependencies': {'pip': ['fastapi', 'sqlalchemy'], 'setup': []},
}

for fw in ['claude-code', 'cursor-cli', 'gemini-cli', 'codex-cli', 'open-code']:
    with tempfile.TemporaryDirectory() as d:
        result = configure_agent(d, task, fw)
        files = []
        for root, dirs, fnames in os.walk(d):
            for f in fnames:
                files.append(os.path.relpath(os.path.join(root, f), d))
        print(f'  {fw}:')
        for f in sorted(files): print(f'    {f}')
        print()
" 2>/dev/null
sleep 3

# ── Final message ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  Pipeline: Goal → PO → Roles → HR Agent → Skills → Template → Config → Agent${RESET}"
echo ""
echo -e "  ${BOLD}18 roles${RESET} across 7 departments"
echo -e "  ${BOLD}20 skills${RESET} with full dependency chains (nix + pip + npm + setup)"
echo -e "  ${BOLD}5 templates${RESET} (YAML, user-extensible, LLM-generated)"
echo -e "  ${BOLD}6 frameworks${RESET} (claude-code, cursor, gemini, codex, open-code, aider)"
echo -e "  ${BOLD}Auto-deploy${RESET} after sprint (detect → test → build → preview)"
echo ""
echo -e "  ${DIM}Open source: github.com/alpibrusl/caloron-noether${RESET}"
echo ""
sleep 3
