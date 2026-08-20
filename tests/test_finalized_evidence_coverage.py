from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "artifacts"
EVALUATIONS = ARTIFACTS / "evaluations"
RESULTS = EVALUATIONS / "release-skill-only-results.tsv"
RESULT_COLUMNS = [
    "task",
    "release_status",
    "reward",
    "tests_passed",
    "tests_skipped",
    "tests_total",
    "condition",
    "background_documents_available",
    "clean_lineage",
    "oracle_agent",
    "model",
    "evidence_sha256",
    "release_skill_tree_sha256",
    "release_background_doc_tree_sha256",
]
SHA256_RE = re.compile(r"[0-9a-f]{64}")


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


def _read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def test_release_has_one_canonical_result_table() -> None:
    assert sorted(path.name for path in EVALUATIONS.iterdir()) == [RESULTS.name]
    columns, rows = _read_tsv(RESULTS)
    assert columns == RESULT_COLUMNS
    assert len(rows) == 62


def test_canonical_results_match_current_validated_release_artifacts() -> None:
    _, status_rows = _read_tsv(ARTIFACTS / "skill_status.tsv")
    validated = {
        row["task"]
        for row in status_rows
        if row["status"].startswith("validated_")
    }
    candidates = {
        row["task"]
        for row in status_rows
        if row["status"].startswith("candidate_")
    }
    _, result_rows = _read_tsv(RESULTS)
    result_tasks = [row["task"] for row in result_rows]

    assert len(status_rows) == 85
    assert len(validated) == 62
    assert len(candidates) == 23
    assert validated.isdisjoint(candidates)
    assert result_tasks == sorted(validated)

    for row in result_rows:
        task = row["task"]
        assert row["release_status"] == "validated_skill_only_full_score"
        assert row["reward"] == "1.0"
        assert int(row["tests_total"]) > 0
        assert int(row["tests_passed"]) + int(row["tests_skipped"]) == int(
            row["tests_total"]
        )
        assert row["condition"] == "skill_only"
        assert row["background_documents_available"] == "false"
        assert row["clean_lineage"] == "verified"
        assert row["oracle_agent"] == "claude-code-skill-only"
        assert row["model"] == "claude-opus-4-6"
        assert SHA256_RE.fullmatch(row["evidence_sha256"])
        assert _tree_digest(ARTIFACTS / "skills" / task) == row[
            "release_skill_tree_sha256"
        ]
        assert _tree_digest(ARTIFACTS / "background_docs" / task) == row[
            "release_background_doc_tree_sha256"
        ]
