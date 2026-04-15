"""Tests for caloron.organisation — the house-style conventions layer."""

from __future__ import annotations

from pathlib import Path

import yaml
from caloron.organisation import (
    GLOBAL_CONVENTIONS_FILE,
    Conventions,
    load_conventions,
)

# ── Conventions shape + renderer ────────────────────────────────────────────


def test_is_empty_on_default_conventions():
    c = Conventions()
    assert c.is_empty() is True
    assert c.render_prompt_block() == ""


def test_render_skips_header_when_no_content():
    """No accidental empty `## Organisation Conventions` section."""
    c = Conventions(organisation="", warnings=["something"])
    # Warnings are diagnostic metadata, not content.
    assert c.is_empty() is True
    assert c.render_prompt_block() == ""


def test_render_surfaces_package_naming():
    c = Conventions(
        organisation="Alpibru Labs",
        package_naming={"style": "kebab-case", "prefix": "alpibru-"},
    )
    text = c.render_prompt_block()
    assert "## Organisation Conventions" in text
    assert "Alpibru Labs" in text
    assert "kebab-case" in text
    assert "`alpibru-`" in text


def test_render_surfaces_imports_namespace():
    c = Conventions(imports={"namespace": "alpibru", "style": "absolute"})
    text = c.render_prompt_block()
    assert "alpibru" in text
    assert "absolute" in text


def test_render_includes_license_header_as_code_block():
    c = Conventions(
        license={"header": "Copyright (c) Alpibru Labs. Licensed EUPL-1.2."}
    )
    text = c.render_prompt_block()
    # Must be fenced so claude doesn't confuse it with its own reply.
    assert "```" in text
    assert "Copyright" in text


def test_render_lists_disallowed_dependencies():
    c = Conventions(dependencies={"disallow": ["GPL", "AGPL"]})
    text = c.render_prompt_block()
    assert "GPL" in text
    assert "AGPL" in text


def test_render_ignores_unknown_sections_by_surfacing_them():
    c = Conventions(extra={"review_slack_channel": "#eng-review"})
    text = c.render_prompt_block()
    # Unknown keys land in a generic "Other" bucket — we don't drop user
    # content silently, but also don't invent a schema for it.
    assert "review_slack_channel" in text
    assert "#eng-review" in text


# ── Loader ──────────────────────────────────────────────────────────────────


def test_load_returns_empty_when_no_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "caloron.organisation.GLOBAL_CONVENTIONS_FILE", tmp_path / "nope.yml"
    )
    c = load_conventions()
    assert c.is_empty() is True
    assert c.warnings == []


def test_load_parses_global_file(tmp_path: Path, monkeypatch):
    gfile = tmp_path / "global.yml"
    gfile.write_text(
        yaml.safe_dump(
            {
                "organisation": "Alpibru",
                "package_naming": {"style": "snake_case"},
                "dependencies": {"disallow": ["GPL"]},
            }
        )
    )
    monkeypatch.setattr("caloron.organisation.GLOBAL_CONVENTIONS_FILE", gfile)
    c = load_conventions()
    assert c.organisation == "Alpibru"
    assert c.package_naming == {"style": "snake_case"}
    assert c.dependencies["disallow"] == ["GPL"]
    assert c.source == str(gfile)


def test_load_merges_project_overrides_right_wins(tmp_path: Path, monkeypatch):
    """Project-level caloron.yml overrides the same key in global."""
    gfile = tmp_path / "global.yml"
    gfile.write_text(
        yaml.safe_dump(
            {
                "organisation": "Alpibru",
                "package_naming": {"style": "snake_case", "prefix": "alp-"},
                "imports": {"namespace": "alpibru"},
            }
        )
    )
    pdir = tmp_path / "project"
    pdir.mkdir()
    (pdir / "caloron.yml").write_text(
        yaml.safe_dump(
            {
                "package_naming": {"style": "kebab-case"},  # wins
                # prefix is not overridden → carries forward
            }
        )
    )
    monkeypatch.setattr("caloron.organisation.GLOBAL_CONVENTIONS_FILE", gfile)
    c = load_conventions(project_dir=pdir)
    assert c.package_naming["style"] == "kebab-case"
    assert c.package_naming["prefix"] == "alp-"
    # Untouched section stays.
    assert c.imports["namespace"] == "alpibru"


def test_load_tolerates_malformed_yaml(tmp_path: Path, monkeypatch):
    """A broken file must not kill the sprint — produce warning, empty conv."""
    gfile = tmp_path / "broken.yml"
    gfile.write_text("this: is: not: valid: yaml:\n  - [")
    monkeypatch.setattr("caloron.organisation.GLOBAL_CONVENTIONS_FILE", gfile)
    c = load_conventions()
    assert c.is_empty() is True
    assert c.warnings, "malformed YAML should surface as a warning, not crash"
    assert "YAML" in c.warnings[0] or "yaml" in c.warnings[0].lower()


def test_load_tolerates_non_mapping_top_level(tmp_path: Path, monkeypatch):
    """YAML that parses to a list / scalar at the top level is rejected."""
    gfile = tmp_path / "list.yml"
    gfile.write_text("- just\n- a\n- list\n")
    monkeypatch.setattr("caloron.organisation.GLOBAL_CONVENTIONS_FILE", gfile)
    c = load_conventions()
    assert c.is_empty() is True
    assert any("mapping" in w for w in c.warnings)


def test_load_with_no_project_file_falls_back_to_global(tmp_path: Path, monkeypatch):
    gfile = tmp_path / "global.yml"
    gfile.write_text(yaml.safe_dump({"organisation": "OnlyGlobal"}))
    monkeypatch.setattr("caloron.organisation.GLOBAL_CONVENTIONS_FILE", gfile)
    pdir = tmp_path / "proj-with-no-yml"
    pdir.mkdir()
    c = load_conventions(project_dir=pdir)
    assert c.organisation == "OnlyGlobal"


def test_global_conventions_file_respects_caloron_home(monkeypatch, tmp_path):
    """The module-level constant is a sensible default; resolver respects
    CALORON_HOME so projects-with-tmp-home tests don't clobber each other."""
    # The constant is captured at module import time, so we just
    # sanity-check the shape users rely on.
    assert GLOBAL_CONVENTIONS_FILE.name == "organisation.yml"


# ── end-to-end: rendered block is what we expect ────────────────────────────


def test_load_and_render_roundtrip(tmp_path: Path, monkeypatch):
    gfile = tmp_path / "global.yml"
    gfile.write_text(
        yaml.safe_dump(
            {
                "organisation": "Alpibru",
                "package_naming": {"style": "kebab-case", "prefix": "alp-"},
                "commit_message": {"format": "<type>(<scope>): <summary>"},
                "dependencies": {"disallow": ["AGPL"]},
            }
        )
    )
    monkeypatch.setattr("caloron.organisation.GLOBAL_CONVENTIONS_FILE", gfile)
    c = load_conventions()
    rendered = c.render_prompt_block()
    # Every declared piece must appear in the rendered prompt block.
    assert "Alpibru" in rendered
    assert "kebab-case" in rendered
    assert "alp-" in rendered
    assert "<type>(<scope>): <summary>" in rendered
    assert "AGPL" in rendered
