#!/usr/bin/env python3
"""Reshape: scope-after-health-binding → decide_intervention input.

After a ``Let { health: check_agent_health }``, the body's scope has
``health: {results}`` nested under the binding name plus the outer
``interventions`` carried through from the sprint_tick input.
``decide_intervention`` expects ``{results, interventions}`` flat.

Input:
  { health: Record { results: List<Any> }, interventions: Any }

Output:
  { results: List<Any>, interventions: Any }

Effects: [Pure]
"""


def execute(input: dict) -> dict:
    health = input.get("health") or {}
    return {
        "results": health.get("results", []),
        "interventions": input.get("interventions", {}),
    }
