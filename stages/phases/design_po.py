#!/usr/bin/env python3
"""Design PO — optional phase slot before architect.

Input:  { goal: Text, constraints: Text }
Output: { goal: Text, constraints: Text, design_brief: Text,
          components_inventory: List[Record] }

This is a no-op pass-through today. Its purpose is to reserve the
phase-boundary slot so future design agents have somewhere to plug in
without changing full_cycle.json or rewiring the downstream stages.
When a real design agent is wired up (figma-mcp, mockup generation,
etc.) its output should:

  - ``design_brief`` — one-paragraph summary of the UX intent, flows,
    and constraints derived from the PRD. Consumed by architect_po to
    scope the component decomposition.
  - ``components_inventory`` — optional list of
    {name, purpose, props, state_variants} records (see the
    corpus/ui-components-inventory.yaml fixture in agentspec for the
    contract). Consumed by architect_po as a prior for component
    naming / interface shape.

Downstream stages handle missing fields gracefully: architect_po
already accepts any input with ``goal`` + ``constraints``; the extra
fields here are additive, not required.

Stage is hermetic — no cross-module imports.
"""

from __future__ import annotations


def execute(input: dict) -> dict:
    goal = str(input.get("goal", ""))
    constraints = str(input.get("constraints", ""))
    if not goal.strip():
        raise ValueError("design_po: 'goal' must be non-empty")

    # Pass-through: preserve the fields architect_po needs, plus empty
    # slots for the design artifacts that a real designer would fill.
    # Keeping them as empty strings / empty lists rather than absent
    # means architect_po can always read them without isinstance dances.
    return {
        "goal": goal,
        "constraints": constraints,
        "design_brief": str(input.get("design_brief", "")),
        "components_inventory": list(input.get("components_inventory") or []),
    }
