from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "artifacts"
BACKFILL_NAME = "claude-opus-4.6-skill-only-evidence-backfill-20260809"


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_every_validated_skill_has_public_full_score_evidence() -> None:
    status_rows = _read_tsv(ARTIFACTS / "skill_status.tsv")
    validated = {
        row["task"]
        for row in status_rows
        if row["status"].startswith("validated_")
    }

    full_score: set[str] = set()
    for path in (ARTIFACTS / "evaluations").glob("*.tsv"):
        for row in _read_tsv(path):
            if row.get("outcome") != "full_score" or row.get("reward") != "1.0":
                continue
            if row.get("release_status", "").startswith("validated_"):
                full_score.add(row["task"])

    assert len(validated) == 64
    assert validated <= full_score


def test_historical_backfill_matches_current_release_artifacts() -> None:
    rows = _read_tsv(
        ARTIFACTS / "evaluations" / f"{BACKFILL_NAME}.tsv"
    )
    assert len(rows) == 9
    assert len({row["task"] for row in rows}) == len(rows)

    for row in rows:
        task = row["task"]
        assert row["release_status"] == "validated_skill_only_full_score"
        assert row["outcome"] == "full_score"
        assert row["reward"] == "1.0"
        assert row["tests_passed"] == row["tests_total"]
        assert row["condition"] == "skill_only"
        assert row["background_documents_available"] == "false"
        assert row["clean_lineage"] == "verified"
        assert row["oracle_agent"] == "claude-code-skill-only"
        assert _tree_digest(ARTIFACTS / "skills" / task) == row[
            "skill_tree_sha256"
        ]
        assert _tree_digest(ARTIFACTS / "background_docs" / task) == row[
            "background_doc_tree_sha256"
        ]

    summary = json.loads(
        (
            ARTIFACTS
            / "evaluations"
            / f"{BACKFILL_NAME}-summary.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["tasks"] == len(rows)
    assert summary["full_score"] == len(rows)
    assert summary["verified_current_skill_tree"] == len(rows)
    assert summary["verified_clean_lineage"] == len(rows)
    assert summary["release_validated_evidence_coverage"] == 64
    legacy = [
        row
        for row in rows
        if row["evidence_source"] == "legacy_verifier_stdout_plus_reward"
    ]
    assert [row["task"] for row in legacy] == [
        "find-topk-similiar-chemicals"
    ]
    assert summary["legacy_verifier_without_ctrf"] == len(legacy)
