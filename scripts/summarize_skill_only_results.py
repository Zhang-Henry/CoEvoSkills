#!/usr/bin/env python3
"""Create a public, trace-free summary of a Skill-only transfer run."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path


def load_statuses(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {
            row["task"]: row["status"]
            for row in csv.DictReader(stream, delimiter="\t")
        }


def require_nonempty_release(statuses: dict[str, str]) -> None:
    if not statuses:
        raise SystemExit("release status manifest contains no tasks")


def safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def load_latest_scores(results_root: Path) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for path in results_root.rglob("results.csv"):
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                task = row.get("task", "")
                if not task:
                    continue
                previous = latest.get(task)
                if previous is None or row.get("started_at", "") >= previous.get(
                    "started_at", ""
                ):
                    latest[task] = row
    return latest


def load_latest_trials(jobs_root: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for path in jobs_root.glob("*/*/*/result.json"):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        task = result.get("task_name")
        if not isinstance(task, str) or not task:
            continue
        previous = latest.get(task)
        if previous is None or result.get("started_at", "") >= previous.get(
            "started_at", ""
        ):
            result["_trial_dir"] = str(path.parent)
            latest[task] = result
    return latest


def skill_was_used(trial: dict | None) -> bool:
    if not trial:
        return False
    agent_dir = Path(trial["_trial_dir"]) / "agent"
    candidates = [
        agent_dir / "codex.txt",
        agent_dir / "claude-code.txt",
        agent_dir / "claude-code.trajectory.json",
        agent_dir / "gemini-cli.trajectory.json",
        agent_dir / "trajectory.json",
    ]
    markers = (
        "/logs/agent/skills/",
        "/app/environment/skills/",
        "/root/.claude/skills/",
        "/root/.gemini/skills/",
    )
    for trace in candidates:
        try:
            content = trace.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in content for marker in markers):
            return True
    return False


def invalid_reason(trial: dict | None) -> str:
    if not trial:
        return "missing_trial_result"
    exception = trial.get("exception_info") or {}
    message = str(exception.get("exception_message", ""))
    if "OPENAI_API_KEY" in message:
        return "verifier_missing_openai_api_key"
    exception_type = str(exception.get("exception_type", ""))
    return f"trial_exception:{exception_type}" if exception_type else "missing_reward"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--jobs-root", type=Path, required=True)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--output-tsv", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--model", default="openai/gpt-5.4")
    parser.add_argument("--agent", default="codex-subscription")
    parser.add_argument("--run-date", default=datetime.now(UTC).date().isoformat())
    args = parser.parse_args()

    statuses = load_statuses(args.status_file)
    require_nonempty_release(statuses)
    scores = load_latest_scores(args.results_root)
    trials = load_latest_trials(args.jobs_root)

    records: list[dict[str, str]] = []
    for task, release_status in sorted(statuses.items()):
        score = scores.get(task)
        trial = trials.get(task)
        if score is None:
            outcome = "infrastructure_invalid"
            reward = tests_passed = tests_total = ""
            note = invalid_reason(trial)
        else:
            reward = score.get("reward", "")
            tests_passed = score.get("tests_passed", "")
            tests_total = score.get("tests_total", "")
            outcome = "full_score" if reward == "1.0" else "not_full_score"
            note = ""
        records.append(
            {
                "task": task,
                "release_status": release_status,
                "outcome": outcome,
                "reward": reward,
                "tests_passed": tests_passed,
                "tests_total": tests_total,
                "skill_used": str(skill_was_used(trial)).lower(),
                "note": note,
            }
        )

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(records[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)

    def count(status_prefix: str | None, outcome: str) -> int:
        return sum(
            row["outcome"] == outcome
            and (
                status_prefix is None
                or row["release_status"].startswith(status_prefix)
            )
            for row in records
        )

    validated_total = sum(
        row["release_status"].startswith("validated_") for row in records
    )
    candidate_total = sum(
        row["release_status"].startswith("candidate_") for row in records
    )
    full = count(None, "full_score")
    scored = sum(row["outcome"] != "infrastructure_invalid" for row in records)
    summary = {
        "run_date": args.run_date,
        "model": args.model,
        "agent": args.agent,
        "condition": "skill_only",
        "background_documents_available": False,
        "benchmark_tasks": len(records),
        "canonical_scores": scored,
        "infrastructure_invalid": len(records) - scored,
        "full_score": full,
        "strict_pass_rate": safe_rate(full, len(records)),
        "scored_only_pass_rate": safe_rate(full, scored),
        "validated": {
            "tasks": validated_total,
            "full_score": count("validated_", "full_score"),
            "pass_rate": safe_rate(
                count("validated_", "full_score"), validated_total
            ),
        },
        "candidate": {
            "tasks": candidate_total,
            "full_score": count("candidate_", "full_score"),
            "strict_pass_rate": safe_rate(
                count("candidate_", "full_score"), candidate_total
            ),
        },
    }
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
