from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.summarize_skill_only_results import (
    invalid_reason,
    load_latest_scores,
    require_nonempty_release,
    safe_rate,
    skill_was_used,
)


def test_latest_score_wins(tmp_path: Path) -> None:
    path = tmp_path / "results.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("task", "started_at", "reward"),
        )
        writer.writeheader()
        writer.writerow({"task": "example", "started_at": "1", "reward": "0.0"})
        writer.writerow({"task": "example", "started_at": "2", "reward": "1.0"})

    assert load_latest_scores(tmp_path)["example"]["reward"] == "1.0"


def test_skill_usage_reads_codex_trace(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "codex.txt").write_text(
        json.dumps({"command": "read /logs/agent/skills/evo-example/SKILL.md"}),
        encoding="utf-8",
    )

    assert skill_was_used({"_trial_dir": str(tmp_path)})


def test_skill_usage_reads_other_agent_traces(tmp_path: Path) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "claude-code.trajectory.json").write_text(
        json.dumps({"path": "/root/.claude/skills/evo-example/SKILL.md"}),
        encoding="utf-8",
    )

    assert skill_was_used({"_trial_dir": str(tmp_path)})


def test_small_custom_release_is_valid_for_summary() -> None:
    require_nonempty_release({"new-task": "candidate_not_finalized"})
    assert safe_rate(0, 0) is None


def test_missing_verifier_key_is_infrastructure_invalid() -> None:
    trial = {
        "exception_info": {
            "exception_type": "ValueError",
            "exception_message": "Environment variable 'OPENAI_API_KEY' not found",
        }
    }

    assert invalid_reason(trial) == "verifier_missing_openai_api_key"
