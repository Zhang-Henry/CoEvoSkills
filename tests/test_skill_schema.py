from __future__ import annotations

import csv
from pathlib import Path

from libs.terminus_agent.evolution.skill_schema import (
    validate_skill_directory,
    validate_skill_markdown,
)


def _codes(content: str, directory: str = "evo-example") -> set[str]:
    return {
        issue.code
        for issue in validate_skill_markdown(
            content,
            directory_name=directory,
            display_path=f"/skills/{directory}/SKILL.md",
        )
    }


def test_valid_anthropic_style_skill_schema() -> None:
    content = """---
name: evo-example
description: "Processes example inputs; use for reproducible example tasks."
---

# Example

Follow the reusable workflow.
"""
    assert _codes(content) == set()


def test_valid_multiline_description_schema() -> None:
    content = """---
name: evo-example
description: >-
  Processes example inputs.
  Use for reproducible example tasks.
---

# Example
"""
    assert _codes(content) == set()


def test_schema_requires_frontmatter_at_byte_zero_and_nonempty_body() -> None:
    assert _codes("\n---\nname: evo-example\ndescription: useful\n---\nbody\n") == {
        "frontmatter_not_at_byte_zero"
    }
    assert _codes("---\nname: evo-example\ndescription: useful\n---\n") == {
        "empty_skill_body"
    }


def test_schema_reports_precise_required_field_errors() -> None:
    codes = _codes("---\nname: \ndescription: \n---\nbody\n")
    assert codes == {"empty_name", "empty_description"}


def test_schema_requires_name_to_match_directory() -> None:
    codes = _codes(
        "---\nname: evo-other\ndescription: useful\n---\nbody\n",
        directory="evo-example",
    )
    assert codes == {"directory_name_mismatch"}


def test_schema_rejects_unknown_top_level_fields_and_ambiguous_description() -> None:
    codes = _codes(
        "---\n"
        "name: evo-example\n"
        "description: handles inputs: when requested\n"
        "answer-key: forbidden\n"
        "---\nbody\n"
    )
    assert codes == {"ambiguous_description_scalar", "unexpected_frontmatter_key"}


def test_directory_validator_returns_safe_exact_messages(tmp_path: Path) -> None:
    skill = tmp_path / "evo-example"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "# Missing frontmatter\n", encoding="utf-8"
    )
    issues = validate_skill_directory(skill)
    assert [issue.code for issue in issues] == ["frontmatter_not_at_byte_zero"]
    assert "byte zero" in issues[0].message


def test_public_artifacts_cover_all_benchmark_tasks() -> None:
    root = Path(__file__).resolve().parents[1]
    benchmark_tasks = {
        path.name
        for path in (root / "tasks").iterdir()
        if path.is_dir() and (path / "task.toml").is_file()
    }
    with (root / "artifacts" / "skill_status.tsv").open(
        encoding="utf-8", newline=""
    ) as stream:
        statuses = list(csv.DictReader(stream, delimiter="\t"))

    background_tasks = {
        path.name
        for path in (root / "artifacts" / "background_docs").iterdir()
        if path.is_dir()
    }
    skill_tasks = {
        path.name
        for path in (root / "artifacts" / "skills").iterdir()
        if path.is_dir()
    }
    assert len(benchmark_tasks) == 85
    assert background_tasks == benchmark_tasks
    assert skill_tasks == benchmark_tasks
    assert {row["task"] for row in statuses} == benchmark_tasks
    assert {row["background_lineage"] for row in statuses} == {"verified"}

    for task in sorted(skill_tasks):
        packages = [
            path for path in (root / "artifacts" / "skills" / task).iterdir()
            if path.is_dir()
        ]
        assert len(packages) == 1, task
        assert validate_skill_directory(packages[0]) == [], task
