"""Phase interface schemas.

The hardest part of multi-role sprints is the *interfaces between phases*:
what shape does "architect" hand to "dev," what does "dev" hand to "review."
If those contracts drift, phases leak into each other and the whole point
of role separation is lost.

This module defines each interface as a plain dataclass + a validator that
stages call on input/output. Keep them minimal — extend only when a
downstream phase actually needs a new field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Architect output → Dev input ─────────────────────────────────────────────


@dataclass
class Component:
    """A discrete unit of work the architect surfaces for the dev phase."""

    name: str
    purpose: str
    interface: str  # Free-form signature / contract description

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Component:
        _require(d, ["name", "purpose", "interface"], "component")
        return cls(name=str(d["name"]), purpose=str(d["purpose"]), interface=str(d["interface"]))


@dataclass
class ArchitectOutput:
    """The artifact produced by the architect phase."""

    design_doc: str
    components: list[Component] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ArchitectOutput:
        _require(d, ["design_doc", "components"], "architect output")
        components = [Component.from_dict(c) for c in d.get("components", [])]
        if not components:
            raise ValueError("architect output must contain at least one component")
        return cls(
            design_doc=str(d["design_doc"]),
            components=components,
            risks=[str(r) for r in d.get("risks", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_doc": self.design_doc,
            "components": [c.__dict__ for c in self.components],
            "risks": self.risks,
        }


# ── Dev output ───────────────────────────────────────────────────────────────


@dataclass
class DevTask:
    """A concrete agent-assignable task emitted by the dev phase."""

    id: str
    title: str
    depends_on: list[str]
    agent_prompt: str
    framework: str = "claude-code"
    component: str = ""  # source component name for traceability

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _require(d: dict[str, Any], keys: list[str], what: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{what} missing required fields: {missing}")
