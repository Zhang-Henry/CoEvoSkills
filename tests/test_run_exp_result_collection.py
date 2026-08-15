from __future__ import annotations

import csv
from pathlib import Path

import run_exp


def test_evolution_result_reports_skill_imported_to_staged_task(
    tmp_path: Path, monkeypatch
) -> None:
    tasks_dir = tmp_path / "prepared" / "evolution-canary"
    skill_dir = (
        tasks_dir
        / "example-task"
        / "environment"
        / "skills"
        / "evo-example"
    )
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: Example.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_exp, "EXPERIMENTS_DIR", tmp_path / "results")
    monkeypatch.setattr(run_exp, "JOBS_DIR", tmp_path / "jobs")

    run_exp.record_run_result(
        {
            "task": "example-task",
            "model": "vertex_ai/claude-opus-4-6",
            "agent": "terminus-2-evolution",
            "tasks_dir": str(tasks_dir),
            "tests_passed": 1,
            "tests_total": 1,
            "reward": 1.0,
            "started_at": "2026-08-13T22:21:36+00:00",
            "duration_sec": 12,
            "job_name": "missing-job-log",
        }
    )

    result_csv = (
        tmp_path
        / "results"
        / "vertex-ai-claude-opus-4-6"
        / "evolution-canary"
        / "example-task"
        / "results.csv"
    )
    with result_csv.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))

    assert row["skills_created"] == "evo-example"
