#!/usr/bin/env python3
"""Architect PO — decompose a goal into components + risks.

Input:  { goal: Text, constraints: Text }
Output: { design_doc: Text, components: List[Record], risks: List[Text] }

Tries the Anthropic API first when ANTHROPIC_API_KEY is set, falling
back to a template decomposition otherwise. Stages are hermetic by
Noether convention — everything needed at runtime lives in this file.
"""

import json as _json
import os
import re
import urllib.error
import urllib.request

# ── LLM call (hermetic; urllib, no SDK) ─────────────────────────────────────


_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-5"


def _llm_call(prompt: str, timeout: int = 60) -> str | None:
    """POST to Anthropic. Returns the response text, or None on any failure."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    model = os.environ.get("CALORON_LLM_MODEL", _DEFAULT_MODEL)
    body = _json.dumps(
        {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        _ANTHROPIC_ENDPOINT,
        data=body,
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            resp = _json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    content = resp.get("content") if isinstance(resp, dict) else None
    if isinstance(content, list) and content:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if isinstance(text, str):
            return text
    return None


def _parse_json_object(text: str) -> dict | None:
    """Extract the first JSON object from ``text``. Tolerant of code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = _json.loads(match.group())
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _validate_arch(data: dict) -> bool:
    """Schema guard for the LLM output."""
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("design_doc"), str) or not data["design_doc"].strip():
        return False
    components = data.get("components")
    if not isinstance(components, list) or not components:
        return False
    for c in components:
        if not isinstance(c, dict):
            return False
        if not all(isinstance(c.get(k), str) and c.get(k) for k in ("name", "purpose", "interface")):
            return False
    risks = data.get("risks", [])
    if not isinstance(risks, list) or not all(isinstance(r, str) for r in risks):
        return False
    return True


def _build_prompt(goal: str, constraints: str) -> str:
    constraints_block = f"\n<constraints>\n{constraints.strip()}\n</constraints>" if constraints.strip() else ""
    return (
        "You are the architect in a multi-role software sprint. Decompose the goal into "
        "2–5 components. Each component has a PascalCase name, a one-sentence purpose, "
        "and a short interface description (function signatures or public surface).\n\n"
        "Return ONLY a single JSON object with this exact shape, no prose:\n"
        "{\n"
        '  "design_doc": "<markdown design document>",\n'
        '  "components": [\n'
        '    {"name": "PascalCaseName", "purpose": "...", "interface": "..."}\n'
        "  ],\n"
        '  "risks": ["<risk 1>", "<risk 2>"]\n'
        "}\n\n"
        f"<goal>\n{goal.strip()}\n</goal>{constraints_block}"
    )


# ── Template fallback (deterministic) ────────────────────────────────────────


def _template_decompose(goal: str, constraints: str) -> dict:
    candidates = re.findall(r"\b([A-Z][a-zA-Z_]{2,})\b", goal)
    seen: set = set()
    names = []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            names.append(c)
    if not names:
        names = ["Core"]

    components = [
        {
            "name": n,
            "purpose": f"Implements the '{n}' responsibility derived from the goal.",
            "interface": f"Public surface for {n}; see design_doc for contract.",
        }
        for n in names[:5]
    ]

    lines = [
        f"# Design — {goal.strip().splitlines()[0][:80]}",
        "",
        "## Goal",
        goal.strip(),
        "",
    ]
    if constraints.strip():
        lines += ["## Constraints", constraints.strip(), ""]
    lines += ["## Components"]
    for c in components:
        lines.append(f"- **{c['name']}** — {c['purpose']}")
    design_doc = "\n".join(lines)

    risks = []
    if len(components) == 1:
        risks.append(
            "Only one component identified — double-check the decomposition "
            "is not hiding a coupled concern."
        )
    if "security" not in goal.lower() and "auth" in goal.lower():
        risks.append("Auth mentioned without explicit security constraints.")

    return {"design_doc": design_doc, "components": components, "risks": risks}


# ── Stage entry point ───────────────────────────────────────────────────────


def execute(input: dict) -> dict:
    goal = str(input.get("goal", ""))
    constraints = str(input.get("constraints", ""))
    if not goal.strip():
        raise ValueError("architect_po: 'goal' must be non-empty")

    # Try the LLM path first; silently fall back on any failure so the
    # stage stays useful in offline / no-key environments (tests, CI).
    llm_text = _llm_call(_build_prompt(goal, constraints))
    if llm_text:
        parsed = _parse_json_object(llm_text)
        if parsed and _validate_arch(parsed):
            # Ensure the caller-visible keys are exactly what we contract.
            return {
                "design_doc": parsed["design_doc"],
                "components": parsed["components"],
                "risks": parsed.get("risks", []),
            }

    return _template_decompose(goal, constraints)
