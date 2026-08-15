from pathlib import Path

from scripts.audit_background_docs import (
    HIGH_RISK_PATTERNS,
    current_input_files,
    input_overlap_findings,
)


def matched_kinds(text: str) -> set[str]:
    return {
        kind
        for kind, pattern in HIGH_RISK_PATTERNS.items()
        if pattern.search(text)
    }


def test_rejects_hidden_distribution_and_metric_gates() -> None:
    text = (
        "At least 70% of all non-UNKNOWN predictions should have detectable "
        "lexical overlap (Jaccard similarity > 0.01). The UNKNOWN rate target "
        "(< 60%) provides enough headroom."
    )
    kinds = matched_kinds(text)
    assert "fixed_population_acceptance_gate" in kinds
    assert "fixed_quality_metric_cutoff" in kinds


def test_rejects_current_recording_region_assumption() -> None:
    text = (
        "Use the last 60% of the video, which is known to contain speech, "
        "as the content-energy reference."
    )
    assert "current_region_assumption" in matched_kinds(text)


def test_allows_public_numeric_domain_facts() -> None:
    text = (
        "Sn63/Pb37 is a eutectic alloy. A one-sided 95% standard-normal "
        "quantile is approximately 1.645."
    )
    assert not matched_kinds(text)


def test_rejects_reference_validator_and_extra_artifact() -> None:
    text = (
        "Plans must also be serialized as pickle files because validation "
        "compares the structured plan against a reference plan."
    )
    kinds = matched_kinds(text)
    assert "reference_evaluation_semantics" in kinds
    assert "undeclared_evaluator_artifact" in kinds


def test_rejects_time_window_override() -> None:
    text = "Do not filter by closedAt date range; simply check current state."
    assert "time_window_semantic_override" in matched_kinds(text)


def test_rejects_current_file_schema_statement() -> None:
    text = (
        "In the context of this task, the population data provides SA2_CODE, "
        "STATE, and POPULATION_2023."
    )
    assert "current_file_schema_statement" in matched_kinds(text)


def test_rejects_current_input_identifier_and_schema_overlap(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "records.csv").write_text(
        "reserve_capacity,description\nGRID_CASE_9087,synthetic current row\n",
        encoding="utf-8",
    )
    doc_path = tmp_path / "task_context_clean" / "doc.md"
    doc_path.parent.mkdir()
    doc_text = (
        "Read reserve_capacity and use GRID_CASE_9087 when applying this workflow."
    )
    doc_path.write_text(doc_text, encoding="utf-8")

    findings = input_overlap_findings(doc_path, doc_text, "", task_dir)
    kinds = {finding["kind"] for finding in findings}
    assert "current_input_schema_key_overlap" in kinds
    assert "current_input_value_overlap" in kinds


def test_instruction_stated_input_literal_is_not_flagged(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "records.csv").write_text(
        "record_id\nCURRENT_ITEM_123\n",
        encoding="utf-8",
    )
    doc_path = tmp_path / "task_context_clean" / "doc.md"
    doc_path.parent.mkdir()
    doc_text = "The instruction names CURRENT_ITEM_123."
    doc_path.write_text(doc_text, encoding="utf-8")

    assert not input_overlap_findings(
        doc_path,
        doc_text,
        "Process CURRENT_ITEM_123",
        task_dir,
    )


def test_scans_inputs_placed_directly_under_environment(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    environment = task_dir / "environment"
    environment.mkdir(parents=True)
    (environment / "workbook.json").write_text(
        '{"CURRENT_SCHEMA_KEY": "CURRENT_ROW_9087"}\n',
        encoding="utf-8",
    )
    doc_dir = environment / "doc"
    doc_dir.mkdir()
    (doc_dir / "background.md").write_text(
        "CURRENT_SCHEMA_KEY must be discovered at runtime.\n",
        encoding="utf-8",
    )

    files = current_input_files(task_dir)
    assert environment / "workbook.json" in files
    assert environment / "doc" / "background.md" not in files
