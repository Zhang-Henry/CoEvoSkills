#!/usr/bin/env python3
"""Audit background documents using only public instructions and supplied input artifacts.

The audit is deliberately conservative. It detects answer-like language,
references to protected evaluation internals, and overlap with current input
identifiers or schemas. It never reads evaluator tests, reference solutions,
golden outputs, model conversations, or prior execution artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTEXT_ROOT = REPO_ROOT / "artifacts" / "background_docs"
DEFAULT_TASK_ROOT = REPO_ROOT / "tasks"
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "background-doc-information-boundary-audit"

HIGH_RISK_PATTERNS = {
    "explicit_answer_language": re.compile(
        r"(?i)\b(?:the\s+)?(?:correct|final|ground[ -]?truth|expected)\s+answer\s+(?:is|=)"
    ),
    "current_instance_conclusion": re.compile(
        r"(?i)\b(?:for|in)\s+(?:the|this)\s+(?:current|provided|supplied)\s+"
        r"(?:instance|dataset|capture|workbook|scenario)\b.{0,100}\b(?:is|are|equals?|=)"
    ),
    "reference_solution_path": re.compile(
        r"(?i)\b(?:reference|official|ground[ -]?truth)\s+(?:patch|solution)\s+"
        r"(?:is|=|at|in|path|tree|file|located)\b"
    ),
    "hidden_evaluator_language": re.compile(
        r"(?i)\b(?:hidden|private)\s+(?:test|evaluator|rubric|threshold|fixture)s?\b"
    ),
    "verifier_shortcut": re.compile(
        r"(?i)\b(?:make|helps?|needed|required)\s+(?:the\s+)?(?:test|verifier|evaluator)s?\s+pass\b"
    ),
    "fixed_population_acceptance_gate": re.compile(
        r"(?i)\b(?:at\s+least|at\s+most|target|must\s+be|should\s+be)\b"
        r".{0,80}\b\d+(?:\.\d+)?\s*%.{0,80}"
        r"\b(?:predictions?|records?|rows?|outputs?|matches?|unknowns?)\b"
    ),
    "fixed_quality_metric_cutoff": re.compile(
        r"(?i)\b(?:jaccard(?:\s+similarity)?|unknown\s+rate|confidence(?:\s+score)?|"
        r"compression\s+percentage)\b.{0,100}"
        r"(?:[<>]=?|below|above|under|over|cutoff|threshold|target)\s*"
        r"\(?\s*\d+(?:\.\d+)?\s*%?"
    ),
    "current_region_assumption": re.compile(
        r"(?i)\b(?:first|last|latter|final)\s+(?:\d+(?:\.\d+)?\s*%|half|portion)"
        r".{0,100}\bknown\s+to\s+contain\b"
    ),
    "reference_evaluation_semantics": re.compile(
        r"(?i)\b(?:validation|validator|verification|tests?)\b.{0,120}"
        r"\b(?:reference\s+(?:plan|solution|output)|compares?\s+(?:the\s+)?"
        r"(?:structured|generated|agent)|loads?\s+(?:this\s+)?(?:pickle|serialized)|"
        r"expected\s+values?\s+positionally)\b"
    ),
    "undeclared_evaluator_artifact": re.compile(
        r"(?i)\b(?:must|required|need)\b.{0,100}\b(?:pickle|\.pkl|serialized\s+plan)\b"
        r".{0,100}\b(?:validation|validator|verification|compare)\b"
    ),
    "time_window_semantic_override": re.compile(
        r"(?i)\bdo\s+not\s+filter\s+by\s+[`'\"]?closedAt|"
        r"\bcurrent\s+state\b.{0,120}\bnot\b.{0,40}\bclosedAt\b"
    ),
    "current_file_schema_statement": re.compile(
        r"(?i)\bin\s+the\s+context\s+of\s+this\s+task\b.{0,160}"
        r"\b(?:data|file|workbook)\s+provides?\b"
    ),
}

COMMON_STRINGS = {
    "application/json",
    "text/plain",
    "utf-8",
    "true",
    "false",
    "none",
    "output",
}

INPUT_DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".txt", ".xlsx", ".xlsm"}
MAX_INPUT_ROWS_PER_FILE = 200_000


def normalized_literal(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.split()).strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(value, ".15g")
    return ""


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def iter_json_literals(value: object, *, prefix: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = normalized_literal(key)
            if key_text:
                yield "schema_key", key_text
            yield from iter_json_literals(child, prefix=f"{prefix}.{key_text}")
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_literals(child, prefix=prefix)
    else:
        text = normalized_literal(value)
        if text:
            yield "value", text


def iter_xlsx_sheet_rows(path: Path) -> Iterator[tuple[str, list[tuple[object, ...]]]]:
    """Yield workbook rows without requiring openpyxl.

    The framework's lightweight host environment intentionally does not always
    install spreadsheet libraries.  Falling back to OOXML prevents XLSX input
    labels and range boundaries from silently disappearing from information-
    boundary audits.
    """
    try:
        import openpyxl

        workbook = openpyxl.load_workbook(
            path,
            read_only=True,
            data_only=False,
        )
        for worksheet in workbook.worksheets:
            rows = [
                tuple(row)
                for row_index, row in enumerate(
                    worksheet.iter_rows(values_only=True)
                )
                if row_index < MAX_INPUT_ROWS_PER_FILE
            ]
            yield worksheet.title, rows
        workbook.close()
        return
    except Exception:
        pass

    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"

    def column_index(reference: str) -> int:
        match = re.match(r"([A-Z]+)", reference.upper())
        if not match:
            return 1
        result = 0
        for character in match.group(1):
            result = result * 26 + ord(character) - ord("A") + 1
        return result

    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in shared_root.findall(f"{{{main_ns}}}si"):
                    shared_strings.append(
                        "".join(
                            node.text or ""
                            for node in item.iter(f"{{{main_ns}}}t")
                        )
                    )

            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships: dict[str, str] = {}
            rel_path = "xl/_rels/workbook.xml.rels"
            if rel_path in archive.namelist():
                rel_root = ET.fromstring(archive.read(rel_path))
                relationships = {
                    node.attrib.get("Id", ""): node.attrib.get("Target", "")
                    for node in rel_root.findall(f"{{{package_rel_ns}}}Relationship")
                }

            sheets = workbook_root.find(f"{{{main_ns}}}sheets")
            if sheets is None:
                return
            for sheet_index, sheet in enumerate(
                sheets.findall(f"{{{main_ns}}}sheet"), 1
            ):
                title = sheet.attrib.get("name", f"Sheet{sheet_index}")
                relation_id = sheet.attrib.get(f"{{{rel_ns}}}id", "")
                target = relationships.get(
                    relation_id,
                    f"worksheets/sheet{sheet_index}.xml",
                ).lstrip("/")
                target_path = (
                    posixpath.normpath(posixpath.join("xl", target))
                    if not target.startswith("xl/")
                    else posixpath.normpath(target)
                )
                if target_path not in archive.namelist():
                    continue
                worksheet_root = ET.fromstring(archive.read(target_path))
                sheet_data = worksheet_root.find(f"{{{main_ns}}}sheetData")
                if sheet_data is None:
                    yield title, []
                    continue
                rows: list[tuple[object, ...]] = []
                for row_index, row in enumerate(
                    sheet_data.findall(f"{{{main_ns}}}row")
                ):
                    if row_index >= MAX_INPUT_ROWS_PER_FILE:
                        break
                    try:
                        worksheet_row = int(row.attrib.get("r", str(row_index + 1)))
                    except ValueError:
                        worksheet_row = row_index + 1
                    while len(rows) < worksheet_row - 1:
                        rows.append(())
                    values: dict[int, object] = {}
                    for cell in row.findall(f"{{{main_ns}}}c"):
                        reference = cell.attrib.get("r", "A1")
                        column = column_index(reference)
                        formula = cell.find(f"{{{main_ns}}}f")
                        cell_type = cell.attrib.get("t", "")
                        value_node = cell.find(f"{{{main_ns}}}v")
                        if formula is not None:
                            value: object = "=" + (formula.text or "")
                        elif cell_type == "inlineStr":
                            value = "".join(
                                node.text or ""
                                for node in cell.iter(f"{{{main_ns}}}t")
                            )
                        elif value_node is None:
                            value = ""
                        elif cell_type == "s":
                            try:
                                value = shared_strings[int(value_node.text or "-1")]
                            except (IndexError, ValueError):
                                value = ""
                        elif cell_type in {"str", "e"}:
                            value = value_node.text or ""
                        else:
                            raw = value_node.text or ""
                            try:
                                value = float(raw)
                                if value.is_integer():
                                    value = int(value)
                            except ValueError:
                                value = raw
                        values[column] = value
                    max_column = max(values, default=0)
                    rows.append(
                        tuple(values.get(column) for column in range(1, max_column + 1))
                    )
                yield title, rows
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return


def iter_input_literals(path: Path) -> Iterator[tuple[str, str]]:
    """Yield current-input schema keys and string cell values.

    This intentionally excludes task tests and solutions. Only supplied input
    artifacts are inspected, so overlap means the Doc may be describing the
    current instance rather than public background knowledge.
    """
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            with path.open(encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.reader(handle)
                for row_index, row in enumerate(reader):
                    if row_index >= MAX_INPUT_ROWS_PER_FILE:
                        break
                    kind = "schema_key" if row_index == 0 else "value"
                    for cell in row:
                        text = normalized_literal(cell)
                        if text:
                            yield kind, text
        except (OSError, csv.Error):
            return
        return

    if suffix in {".json", ".jsonl"}:
        try:
            if suffix == ".jsonl":
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for line_index, line in enumerate(handle):
                        if line_index >= MAX_INPUT_ROWS_PER_FILE:
                            break
                        try:
                            yield from iter_json_literals(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            else:
                yield from iter_json_literals(
                    json.loads(path.read_text(encoding="utf-8", errors="replace"))
                )
        except (OSError, json.JSONDecodeError):
            return
        return

    if suffix in {".xlsx", ".xlsm"}:
        for sheet_name, rows in iter_xlsx_sheet_rows(path):
            yield "sheet_name", sheet_name
            for row_index, row in enumerate(rows):
                kind = "schema_key" if row_index == 0 else "value"
                for cell in row:
                    text = normalized_literal(cell)
                    if text and not text.startswith("="):
                        yield kind, text
        return

    if suffix == ".txt":
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line_index, line in enumerate(handle):
                    if line_index >= MAX_INPUT_ROWS_PER_FILE:
                        break
                    text = normalized_literal(line)
                    if text:
                        yield "value", text
        except OSError:
            return


def current_input_files(task_dir: Path) -> list[Path]:
    """Return supplied instance artifacts without reading tests or solutions.

    Several benchmark tasks place their workbook or text input directly under
    ``environment/`` rather than ``environment/data/``.  Scanning only the
    latter silently missed exactly the instance layouts this audit is meant to
    protect.  Documentation and Skill directories are excluded because they
    are treatment artifacts, not task inputs.  Verifier and evolution-state
    directories are runtime framework artifacts and must not be treated as
    user-supplied instance data either.
    """
    candidates: set[Path] = set()
    environment_root = task_dir / "environment"
    if environment_root.is_dir():
        for path in environment_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in INPUT_DATA_SUFFIXES:
                continue
            relative_parts = path.relative_to(environment_root).parts
            if relative_parts and relative_parts[0] in {
                "doc",
                "skills",
                "verifier",
                ".evolution",
            }:
                continue
            candidates.add(path)

    data_root = task_dir / "data"
    if data_root.is_dir():
        candidates.update(
            path
            for path in data_root.rglob("*")
            if path.is_file() and path.suffix.lower() in INPUT_DATA_SUFFIXES
        )
    return sorted(candidates)


def input_overlap_findings(
    path: Path,
    text: str,
    instruction: str,
    task_dir: Path,
) -> list[dict]:
    lower = text.lower()
    instruction_lower = instruction.lower()
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for input_path in current_input_files(task_dir):
        relative_input = str(input_path.relative_to(task_dir))
        per_file = 0
        for source_kind, value in iter_input_literals(input_path):
            if per_file >= 80:
                break
            normalized = value.lower()
            if (
                len(value) < 5
                or normalized in instruction_lower
                or normalized not in lower
                or value.startswith(("http://", "https://", "/"))
                or normalized in COMMON_STRINGS
            ):
                continue

            identifier_like = bool(
                re.fullmatch(
                    r"(?=.*[A-Za-z])(?=.*[0-9_./:|+-])[A-Za-z0-9_./:|+ -]{6,}",
                    value,
                )
            )
            long_value = len(value) >= 18 and len(value.split()) >= 2
            custom_schema = source_kind == "schema_key" and bool(
                re.fullmatch(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+", value)
            )
            sheet_layout = source_kind == "sheet_name" and len(value) >= 8
            if not (identifier_like or long_value or custom_schema or sheet_layout):
                continue

            key = (source_kind, normalized)
            if key in seen:
                continue
            seen.add(key)
            position = lower.find(normalized)
            findings.append(
                {
                    "severity": "blocker",
                    "kind": f"current_input_{source_kind}_overlap",
                    "file": display_path(path),
                    "line": text.count("\n", 0, position) + 1,
                    "evidence": f"{relative_input}: {value}"[:220],
                }
            )
            per_file += 1
    return findings


def instruction_text(task_dir: Path) -> str:
    for name in ("instruction.md", "task.md"):
        path = task_dir / name
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def audit_task(task: str, docs: list[Path], task_root: Path) -> dict:
    instruction = instruction_text(task_root / task)
    findings: list[dict] = []

    for path in docs:
        text = path.read_text(encoding="utf-8", errors="replace")
        lower = text.lower()
        findings.extend(
            input_overlap_findings(
                path,
                text,
                instruction,
                task_root / task,
            )
        )
        for kind, pattern in HIGH_RISK_PATTERNS.items():
            for match in pattern.finditer(text):
                context = lower[max(0, match.start() - 80):match.end() + 40]
                if (
                    kind != "time_window_semantic_override"
                    and re.search(r"\b(?:do not|don't|never|not|without|rather than)\b", context)
                ):
                    continue
                findings.append(
                    {
                        "severity": "blocker",
                        "kind": kind,
                        "file": str(path.relative_to(REPO_ROOT)),
                        "line": text.count("\n", 0, match.start()) + 1,
                        "evidence": " ".join(match.group(0).split())[:180],
                    }
                )

    unique = []
    seen = set()
    for finding in findings:
        key = tuple(sorted(finding.items()))
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return {"task": task, "documents": len(docs), "findings": unique}


def write_markdown(path: Path, payload: dict) -> None:
    lines = [
        "# Background document information-boundary audit",
        "",
        "This report uses only public instructions and supplied input artifacts; it never reads protected evaluation data.",
        "",
        f"- Documents: {payload['summary']['documents']}",
        f"- Blockers: {payload['summary']['blockers']}",
        f"- Review warnings: {payload['summary']['review_warnings']}",
        "",
        "## Findings",
        "",
        "| Task | Severity | Kind | File | Evidence |",
        "|---|---|---|---|---|",
    ]
    for task in payload["tasks"]:
        for finding in task["findings"]:
            evidence = str(finding.get("evidence", "")).replace("|", "\\|")
            lines.append(
                f"| {task['task']} | {finding['severity']} | {finding['kind']} | "
                f"{finding['file']} | {evidence} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context-root", type=Path, default=DEFAULT_CONTEXT_ROOT)
    parser.add_argument("--task-root", type=Path, default=DEFAULT_TASK_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fail-on-blocker", action="store_true")
    args = parser.parse_args()

    context_root = args.context_root.resolve()
    task_root = args.task_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for task_dir in sorted(path for path in context_root.iterdir() if path.is_dir()):
        docs = sorted(task_dir.rglob("*.md"))
        if docs:
            tasks.append(audit_task(task_dir.name, docs, task_root))

    severity = Counter(
        finding["severity"]
        for task in tasks
        for finding in task["findings"]
    )
    payload = {
        "summary": {
            "tasks": len(tasks),
            "documents": sum(task["documents"] for task in tasks),
            "blockers": severity["blocker"],
            "review_warnings": severity["review"],
        },
        "tasks": tasks,
    }
    (output_dir / "audit.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(output_dir / "audit.md", payload)
    print(json.dumps(payload["summary"], indent=2))
    return 1 if args.fail_on_blocker and severity["blocker"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
