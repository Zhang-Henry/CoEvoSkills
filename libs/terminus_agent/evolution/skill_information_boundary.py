"""Static information-boundary checks for evolved Skills.

The treatment must be a reusable procedure, not a serialized answer for the
current task instance. These checks run before surrogate or GT evaluation and
use only the public instruction plus supplied input artifacts.
"""

from __future__ import annotations

import ast
import builtins
import keyword
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scripts.audit_background_docs import (
    current_input_files,
    iter_input_literals,
    iter_xlsx_sheet_rows,
)


@dataclass(frozen=True)
class SkillBoundaryIssue:
    kind: str
    file: str
    line: int
    evidence: str


_COMMON_NUMBERS = {0.0, 1.0, 2.0, 10.0, 100.0}
_INSTANCE_PARAMETER_NAMES = re.compile(
    r"(?i)(?:num_?)?(?:days?|nights?|city|cities|stops?|travell?ers?|people|persons?)|"
    r"party(?:_size)?|group(?:_size)?|budget|start_?date|end_?date|"
    r"origin|destination|cuisines?"
)
_CAMERA_CALIBRATION_NAMES = re.compile(
    r"(?i)(?:roll|pan|tilt|yaw|pitch|scale|zoom|translation|rotation)"
)
_INSTANCE_ALIAS_NAMES = re.compile(
    r"(?i)(?:alias|aliases|known_?prefix|special_?case|exception)"
)
_CURRENT_RANGE_PARAMETER_NAMES = re.compile(
    r"(?i)(?:(?:start|first|min|end|last|max|data|header|label)_"
    r"(?:year|row|col|column|index)|(?:year|row|col|column|index)_"
    r"(?:start|first|min|end|last|max))"
)
_SPREADSHEET_RANGE = re.compile(
    r"(?<![A-Za-z0-9_])(?:'[^'\n]+'!)?\$?[A-Z]{1,3}\$?\d+"
    r"(?::\$?[A-Z]{1,3}\$?\d+)?(?![A-Za-z0-9_])"
)
_SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".scala", ".go",
    ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".erl", ".ex", ".exs",
    ".sh", ".css", ".html", ".toml", ".yaml", ".yml", ".xml",
    ".gradle", ".kts",
}
_ARTIFACT_SUFFIXES = {
    ".csv", ".json", ".jsonl", ".txt", ".xlsx", ".xlsm", ".xls",
    ".pdf", ".docx", ".pptx", ".mp4", ".mov", ".avi", ".mkv",
    ".wav", ".mp3", ".flac", ".png", ".jpg", ".jpeg", ".pcap",
    ".pcapng", ".db", ".sqlite", ".civ6map", ".zip", ".tar", ".gz",
}
_SOURCE_IDENTIFIER = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]{7,}(?![A-Za-z0-9_])")
_GENERIC_SOURCE_IDENTIFIERS = {
    *(name.lower() for name in keyword.kwlist),
    *(name.lower() for name in dir(builtins)),
    "annotation", "application", "arguments", "attribute", "boolean",
    "callback", "component", "configuration", "constructor", "container",
    "context", "controller", "dependency", "description", "dictionary",
    "document", "element", "environment", "exception", "function",
    "generated", "handler", "identifier", "implementation", "interface",
    "javascript", "metadata", "optional", "parameter", "properties",
    "repository", "request", "response", "runtime", "serializer", "service",
    "settings", "subprocess", "timestamp", "typescript", "validation",
    # Public unified-planning API vocabulary. Airport/PDDL Skills must be able
    # to document an installed planner without that being mistaken for a rare
    # identifier copied from the current task's validator source.
    "unified_planning", "oneshotplanner", "planvalidator", "parse_problem",
    "validate_plan", "problem_kind",
}
_SOURCE_IDENTIFIER_EXCLUDED_PARTS = {
    "doc", "docs", "skills", "verifier", "tests", "test", "testing",
    "solution", "solutions", "reference", "references", "fixtures",
    ".evolution", ".git", "node_modules", ".next", "dist", "build",
    "target", "__pycache__", ".tox", ".venv", "vendor",
}
_GIT_HISTORY_ORACLE_COMMANDS = {
    "log", "show", "reflog", "rev-list", "cat-file", "format-patch",
}
_SECURITY_SENSITIVE_CONTRACT = re.compile(
    r"(?i)\b(?:security|vulnerab(?:ility|le)?|exploit|cve|injection|"
    r"untrusted|attacker|arbitrary\s+code)\b"
)
_EXACT_BOOLEAN_POLICY = re.compile(
    r"(?ix)"
    r"(?:"
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:allow|deny|enable|disable|input|inject|"
    r"override|execute|trusted|security|permission|auth)[A-Za-z0-9_]*\s*=\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_.]*\.)?(?:true|false)\b"
    r"|"
    r"\b[A-Za-z_][A-Za-z0-9_.]*\.(?:true|false)\b"
    r"|"
    r"\b[A-Za-z_][A-Za-z0-9_.]*\([^()\n]{0,180},\s*(?:true|false)\s*\)"
    r")"
)
_PRESCRIPTIVE_SECURITY_TREATMENT = re.compile(
    r"(?i)\b(?:add|apply|assert|check|construct|disable|enable|enforce|expect|"
    r"fix|must|override|patch|reject|replace|require|return|set|validate|write)\b"
)

# Positive qualifiers in a flat output field are assertions, not decorations.
# Keep this deliberately semantic and answer-free: the gate never knows the
# current expected entity or value.  It only requires the reusable Skill to
# prove a requested hard property from an explicit positive source state for
# the same entity before it emits an affirmative qualifier.
_HARD_PROPERTY_QUALIFIER = re.compile(
    r"(?ix)\b(?:"
    # Underscores normally denote API keys/request flags (``pet_friendly``),
    # not a human-readable affirmative qualifier emitted in an artifact.
    r"pet(?:[-\s]+)friendly|wheelchair(?:[-\s]+)accessible|"
    r"[a-z][a-z0-9]*(?:[-\s]+)(?:friendly|accessible|compliant|"
    r"certified|approved|verified)"
    r")\b"
)
_EVIDENCE_CALL_NAME = re.compile(
    r"(?i)(?:classif|evidence|policy|property|support|verify|permission|eligib)"
)
_EVIDENCE_SOURCE_NAME = re.compile(
    r"(?i)(?:record|row|source|metadata|policy|rule|attribute|evidence|status|state)"
)
_EVIDENCE_ASSIGNMENT_NAME = re.compile(
    r"(?i)(?:token|pattern|keyword|positive|negative|unknown|evidence|policy|rule)"
)
_STRUCTURED_MAP_SUFFIXES = {".civ6map", ".mbtiles", ".gpkg", ".sqlite", ".db"}
_STRUCTURED_GEOMETRY_NAME = re.compile(
    r"(?i)^(?:(?:map_?)?(?:width|height|rows?|cols?|columns?)|"
    r"n_?(?:rows?|cols?|columns?)|wrap_?[xy]|(?:horizontal|vertical)_wrap)$"
)
_RANKED_SEARCH_NAME = re.compile(
    r"(?i)(?:candidate|score|rank|option|placement|solution|state|beam|result|"
    r"city_?center|tile)"
)
_STATIC_RULE_OPTIONS_NAME = re.compile(
    r"(?i)(?:option|candidate|categor|district|rule|type|specialty|"
    r"no_?bonus|priority|strategic_?resource|luxury_?resource)"
)
_MAP_AXIS_NAME = re.compile(
    r"(?i)^(?:[xy]|[cr]?[xy]|row|col|column|map_?(?:x|y|row|col|column))$"
)
_EXACT_SOURCE_MUTATION_CALL = re.compile(
    r"(?i)(?:add_?exclusion|fix|migrat|patch|replace|rewrite|transform|update)"
)


def _public_contract_text(task_dir: Path, instruction: str) -> str:
    """Combine instruction and public background document text for declaration checks."""
    parts = [instruction]
    doc_root = task_dir / "environment" / "doc"
    if doc_root.is_dir():
        for path in sorted(doc_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(parts)


def _distinctive_source_identifier(value: str) -> bool:
    """Keep project-local names while excluding language/API vocabulary."""
    normalized = value.lstrip("_").lower()
    if len(normalized) < 8 or normalized in _GENERIC_SOURCE_IDENTIFIERS:
        return False
    has_snake_shape = "_" in value.lstrip("_")
    has_camel_shape = bool(re.search(r"[a-z0-9][A-Z]", value))
    private_shape = value.startswith("_") and len(normalized) >= 10
    return has_snake_shape or has_camel_shape or private_shape or len(normalized) >= 16


def _current_source_identifier_index(
    task_dir: Path,
    public_contract: str,
) -> dict[str, str]:
    """Index rare identifiers from visible current source/config files.

    Tests, verifier assets, solutions, generated build trees, dependencies, and
    public instruction/background document vocabulary are excluded.  Requiring rarity and
    identifier shape avoids treating ordinary standard-library/API names as a
    current-instance shortcut.
    """
    environment_root = task_dir / "environment"
    if not environment_root.is_dir():
        return {}
    occurrences: Counter[str] = Counter()
    paths: dict[str, set[Path]] = defaultdict(set)
    for source in environment_root.rglob("*"):
        if not source.is_file() or source.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        relative = source.relative_to(environment_root)
        if any(part.lower() in _SOURCE_IDENTIFIER_EXCLUDED_PARTS for part in relative.parts):
            continue
        try:
            source_text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for identifier in _SOURCE_IDENTIFIER.findall(source_text):
            if (
                not _distinctive_source_identifier(identifier)
                or _stated_by_instruction(identifier, public_contract)
            ):
                continue
            occurrences[identifier] += 1
            paths[identifier].add(relative)
    return {
        identifier: next(iter(identifier_paths)).as_posix()
        for identifier, identifier_paths in paths.items()
        if occurrences[identifier] <= 12 and len(identifier_paths) <= 2
    }


def _instruction_numbers(instruction: str) -> set[float]:
    values: set[float] = set()
    for raw in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w|\.\d)", instruction):
        try:
            values.add(float(raw))
        except ValueError:
            continue
    return values


def _line_for(text: str, needle: str) -> int:
    position = text.lower().find(needle.lower())
    return text.count("\n", 0, max(0, position)) + 1


def _stated_by_instruction(
    value: str,
    instruction: str,
    *,
    instruction_lower: str | None = None,
    instruction_normalized: str | None = None,
) -> bool:
    """Allow spelling-equivalent public terms such as ``Vendor ID``/``vendor_id``."""
    if instruction_lower is None:
        instruction_lower = instruction.lower()
    if value.lower() in instruction_lower:
        return True
    normalized_value = re.sub(r"[^a-z0-9]+", "", value.lower())
    if instruction_normalized is None:
        instruction_normalized = re.sub(r"[^a-z0-9]+", "", instruction_lower)
    return len(normalized_value) >= 5 and normalized_value in instruction_normalized


def _input_literal_components(source_kind: str, value: str) -> list[str]:
    """Return conservative entity/range components of one input literal.

    Spreadsheet headers often store an entity as ``Entity: description``.  A
    Skill that special-cases only ``Entity`` previously evaded the full-cell
    overlap check and the three-label cluster threshold.  Date tokens such as
    ``1990M1`` similarly need their year component for default-range auditing.
    """
    components = [value]
    if source_kind == "value" and re.search(r"[>|]", value):
        components.extend(re.split(r"\s*[>|]\s*", value))
    if source_kind in {"value", "schema_key"} and ":" in value:
        prefix = value.split(":", 1)[0].strip()
        if 3 <= len(prefix) <= 80:
            components.append(prefix)
    year_match = re.match(r"^((?:19|20)\d{2})(?:M\d{1,2})?\b", value.strip())
    if year_match:
        components.append(year_match.group(1))
    return list(dict.fromkeys(component for component in components if component.strip()))


def _relevant_current_input_literals(
    task_dir: Path,
    skill_texts: tuple[str, ...],
) -> dict[Path, tuple[tuple[str, str], ...]]:
    """Read current inputs once and retain only literals that may match a Skill.

    ``_input_overlap_issues`` can only emit an issue when either the complete
    literal or one of its hierarchy components occurs in a candidate Skill.
    Filtering on that necessary condition preserves the audit result while
    avoiding a repeated scan of large inputs for every file in the Skill.
    """
    skill_lowers = tuple(text.lower() for text in skill_texts)

    # A direct ``candidate in skill_text`` for every value is prohibitively
    # expensive for inputs with hundreds of thousands of rows.  Build exact
    # per-length substring indexes for short values and a fixed-width anchor
    # index for longer values.  The anchor check is only a necessary-condition
    # prefilter; every surviving long value still receives the original exact
    # per-file substring test, so audit semantics are unchanged.  Constructing
    # grams within each file also prevents false matches across file boundaries.
    max_anchor = 12
    grams_by_length: dict[int, set[str]] = {}

    def grams(length: int) -> set[str]:
        indexed = grams_by_length.get(length)
        if indexed is None:
            indexed = {
                text[offset : offset + length]
                for text in skill_lowers
                for offset in range(max(0, len(text) - length + 1))
            }
            grams_by_length[length] = indexed
        return indexed

    def occurs_in_skill(candidate: str) -> bool:
        normalized = candidate.strip().lower()
        if not normalized:
            return False
        if len(normalized) <= max_anchor:
            return normalized in grams(len(normalized))
        anchors = (
            normalized[:max_anchor],
            normalized[
                (len(normalized) - max_anchor) // 2 :
                (len(normalized) - max_anchor) // 2 + max_anchor
            ],
            normalized[-max_anchor:],
        )
        anchor_index = grams(max_anchor)
        if any(anchor not in anchor_index for anchor in anchors):
            return False
        return any(normalized in skill_lower for skill_lower in skill_lowers)

    cached: dict[Path, tuple[tuple[str, str], ...]] = {}
    for input_path in current_input_files(task_dir):
        relevant: list[tuple[str, str]] = []
        for source_kind, value in iter_input_literals(input_path):
            candidates = _input_literal_components(source_kind, value)
            if any(occurs_in_skill(candidate) for candidate in candidates):
                relevant.append((source_kind, value))
        cached[input_path] = tuple(relevant)
    return cached


def _input_overlap_issues(
    skill_file: Path,
    text: str,
    task_dir: Path,
    instruction: str,
    skill_root: Path,
    input_literals_by_path: Mapping[
        Path, tuple[tuple[str, str], ...]
    ] | None = None,
) -> list[SkillBoundaryIssue]:
    lower = text.lower()
    instruction_lower = instruction.lower()
    instruction_normalized = re.sub(r"[^a-z0-9]+", "", instruction_lower)
    issues: list[SkillBoundaryIssue] = []
    seen: set[tuple[str, str]] = set()

    input_items = (
        input_literals_by_path.items()
        if input_literals_by_path is not None
        else (
            (input_path, iter_input_literals(input_path))
            for input_path in current_input_files(task_dir)
        )
    )
    for input_path, input_literals in input_items:
        per_file = 0
        clustered_values: list[str] = []
        clustered_seen: set[str] = set()
        for source_kind, value in input_literals:
            if per_file >= 60:
                break
            normalized = value.lower()
            # Collect several simple labels as a group even when the complete
            # cell is a hierarchy path that is not copied verbatim.
            if source_kind == "value":
                components = _input_literal_components(source_kind, value)
                for component in components:
                    candidate = component.strip()
                    normalized_candidate = candidate.lower()
                    if (
                        4 <= len(candidate) <= 80
                        and not re.fullmatch(r"-?(?:\d+\.\d+|\d+)", candidate)
                        and not candidate.startswith(("http://", "https://", "/"))
                        and re.search(
                            rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])",
                            text,
                            re.IGNORECASE,
                        )
                        and not _stated_by_instruction(
                            candidate,
                            instruction,
                            instruction_lower=instruction_lower,
                            instruction_normalized=instruction_normalized,
                        )
                        and normalized_candidate not in clustered_seen
                    ):
                        clustered_seen.add(normalized_candidate)
                        clustered_values.append(candidate)
                        if (
                            candidate != value
                            and re.search(
                                rf"(?i)(?:['\"]){re.escape(candidate)}(?:['\"])",
                                text,
                            )
                        ):
                            key = ("component", normalized_candidate)
                            if key not in seen:
                                seen.add(key)
                                issues.append(
                                    SkillBoundaryIssue(
                                        kind="current_input_control_literal",
                                        file=str(skill_file.relative_to(skill_root)),
                                        line=_line_for(text, candidate),
                                        evidence=(
                                            f"embeds current input label {candidate!r} from "
                                            f"{input_path.relative_to(task_dir)} as a literal; "
                                            "derive entity normalization from runtime metadata"
                                        )[:180],
                                    )
                                )
                                per_file += 1
            if (
                len(value) < 5
                or normalized not in lower
                or value.startswith(("http://", "https://", "/"))
                or _stated_by_instruction(
                    value,
                    instruction,
                    instruction_lower=instruction_lower,
                    instruction_normalized=instruction_normalized,
                )
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
            current_sheet = source_kind == "sheet_name" and len(value) >= 8
            quoted_current_value = source_kind == "value" and bool(
                re.search(
                    rf"(?i)(?:['\"]){re.escape(value)}(?:['\"])",
                    text,
                )
            )
            precise_current_number = False
            if source_kind == "value" and re.fullmatch(
                r"-?(?:\d+\.\d+|\d+)", value
            ):
                try:
                    numeric_value = abs(float(value))
                    fractional_digits = (
                        len(value.rsplit(".", 1)[1].rstrip("0")) if "." in value else 0
                    )
                    precise_current_number = fractional_digits >= 3 or numeric_value >= 10_000
                except ValueError:
                    precise_current_number = False
            if not (
                identifier_like
                or long_value
                or custom_schema
                or current_sheet
                or quoted_current_value
                or precise_current_number
            ):
                continue
            key = (source_kind, normalized)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                SkillBoundaryIssue(
                    kind=f"current_input_{source_kind}",
                    file=str(skill_file.relative_to(skill_root)),
                    line=_line_for(text, value),
                    evidence=(
                        f"matches {input_path.relative_to(task_dir)}: {value}"
                    )[:180],
                )
            )
            per_file += 1
        if len(clustered_values) >= 3:
            evidence_values = ", ".join(repr(value) for value in clustered_values[:6])
            issues.append(
                SkillBoundaryIssue(
                    kind="current_input_literal_cluster",
                    file=str(skill_file.relative_to(skill_root)),
                    line=min(_line_for(text, value) for value in clustered_values),
                    evidence=(
                        f"embeds {len(clustered_values)} current labels from "
                        f"{input_path.relative_to(task_dir)}: {evidence_values}"
                    )[:180],
                )
            )
    return issues


def _current_input_range_boundaries(task_dir: Path) -> dict[float, list[str]]:
    """Collect high-confidence range/layout boundaries from supplied inputs."""
    boundaries: dict[float, list[str]] = defaultdict(list)

    def remember(value: int | float, evidence: str) -> None:
        numeric = float(value)
        if numeric not in {0.0, 1.0} and evidence not in boundaries[numeric]:
            boundaries[numeric].append(evidence)

    for input_path in current_input_files(task_dir):
        relative = input_path.relative_to(task_dir)
        suffix = input_path.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            try:
                for worksheet_name, rows in iter_xlsx_sheet_rows(input_path):
                    occupied_rows: set[int] = set()
                    occupied_cols: set[int] = set()
                    years: list[int] = []
                    row_columns: dict[int, list[int]] = defaultdict(list)
                    for row_index, row in enumerate(rows, 1):
                        for column_index, cell_value in enumerate(row, 1):
                            if cell_value is None or cell_value == "":
                                continue
                            occupied_rows.add(row_index)
                            occupied_cols.add(column_index)
                            row_columns[row_index].append(column_index)
                            rendered = str(cell_value).strip()
                            match = re.match(r"^((?:19|20)\d{2})(?:M\d{1,2})?\b", rendered)
                            if match:
                                years.append(int(match.group(1)))
                    sheet_evidence = f"{relative}:{worksheet_name}"
                    if occupied_rows:
                        remember(min(occupied_rows), f"first occupied row of {sheet_evidence}")
                        remember(max(occupied_rows), f"last occupied row of {sheet_evidence}")
                    if occupied_cols:
                        remember(min(occupied_cols), f"first occupied column of {sheet_evidence}")
                        remember(max(occupied_cols), f"last occupied column of {sheet_evidence}")
                    if years:
                        remember(min(years), f"first observed year of {sheet_evidence}")
                        remember(max(years), f"last observed year of {sheet_evidence}")
                    for row_index, columns in row_columns.items():
                        ordered = sorted(set(columns))
                        run: list[int] = []
                        for column in [*ordered, -1]:
                            if run and column == run[-1] + 1:
                                run.append(column)
                                continue
                            if len(run) >= 2:
                                remember(
                                    run[0],
                                    f"first column of a current table block in "
                                    f"{sheet_evidence} row {row_index}",
                                )
                                remember(
                                    run[-1],
                                    f"last column of a current table block in "
                                    f"{sheet_evidence} row {row_index}",
                                )
                            run = [column] if column >= 0 else []
            except Exception:
                continue
        elif suffix == ".csv":
            try:
                import csv

                with input_path.open(
                    encoding="utf-8", errors="replace", newline=""
                ) as handle:
                    rows = list(csv.reader(handle))
                if rows:
                    remember(len(rows), f"row count of {relative}")
                    remember(max(len(row) for row in rows), f"column count of {relative}")
            except (OSError, csv.Error):
                continue
    return boundaries


def _current_input_range_default_issues(
    path: Path,
    text: str,
    public_contract: str,
    task_dir: Path,
    skill_root: Path,
    boundaries: Mapping[float, list[str]],
) -> list[SkillBoundaryIssue]:
    """Reject defaults copied from the current input's range or layout."""
    if not boundaries:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    public_numbers = _instruction_numbers(public_contract)
    issues: list[SkillBoundaryIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional = list(node.args.posonlyargs) + list(node.args.args)
        defaults = [None] * (len(positional) - len(node.args.defaults)) + list(
            node.args.defaults
        )
        pairs = list(zip(positional, defaults)) + list(
            zip(node.args.kwonlyargs, node.args.kw_defaults)
        )
        for argument, default in pairs:
            if default is None or not _CURRENT_RANGE_PARAMETER_NAMES.fullmatch(
                argument.arg
            ):
                continue
            value = _constant_numeric_expression(default)
            if (
                value is None
                or value in public_numbers
                or value not in boundaries
            ):
                continue
            evidence_options = boundaries[value]
            dimension = (
                "column"
                if re.search(r"(?i)(?:col|column)", argument.arg)
                else "row"
                if re.search(r"(?i)row", argument.arg)
                else "year"
                if re.search(r"(?i)year", argument.arg)
                else ""
            )
            boundary_evidence = next(
                (
                    evidence
                    for evidence in evidence_options
                    if dimension and dimension in evidence
                ),
                evidence_options[0],
            )
            issues.append(
                SkillBoundaryIssue(
                    kind="current_input_range_default",
                    file=str(path.relative_to(skill_root)),
                    line=getattr(default, "lineno", getattr(node, "lineno", 1)),
                    evidence=(
                        f"{argument.arg}={value:g} matches the {boundary_evidence} "
                        "but is not declared by the public contract; discover it at runtime"
                    )[:220],
                )
            )
    return issues


def _instruction_instance_literals(instruction: str) -> list[str]:
    """Extract high-confidence values from a quoted current-user request.

    Output schemas, thresholds, and format examples are reusable contract, but
    a long quoted request commonly contains current entities and constraints.
    Those values may be read at runtime; serializing several into a Skill turns
    the treatment into an answer for one benchmark instance.
    """
    quoted = re.findall(r'["“]([^"”]{40,})["”]', instruction, re.DOTALL)
    if not quoted:
        return []
    request = quoted[0]
    values: set[str] = set()
    number_words = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    }
    patterns = (
        r"\$\s*\d[\d,]*(?:\.\d+)?",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\b",
        r"\b\d{4}\b",
        r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)[ -](?:day|night|city|travell?er|person)s?\b",
        r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:days?|nights?|cities|travell?ers?|people|persons?)\b",
        r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+cuisines?\b",
    )
    for pattern in patterns:
        values.update(match.group(0).strip() for match in re.finditer(pattern, request))
    for match in re.finditer(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"(?=[ -](?:days?|nights?|city|cities|travell?ers?|people|persons?)\b)",
        request,
        re.IGNORECASE,
    ):
        raw = match.group(1).lower()
        values.add(number_words.get(raw, raw))
    for match in re.finditer(
        r"\bfor\s+(one|two|three|four|five|six|seven|eight|nine|ten)\b",
        request,
        re.IGNORECASE,
    ):
        values.add(number_words[match.group(1).lower()])
    for pattern in (
        r"\b(?:from|in|covering|to)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})",
        r"\b([A-Z][a-z]+)(?=,?\s+(?:Mediterranean|Chinese|Italian|American)(?:\s|,|$))",
    ):
        values.update(match.group(1).strip() for match in re.finditer(pattern, request))
    values.update(
        match.group(1)
        for match in re.finditer(
            r"\b(American|Mediterranean|Chinese|Italian|Indian|Japanese|Korean|Thai|French|Mexican)\b(?=\s+cuisines?|\s*[,])",
            request,
        )
    )
    return sorted(
        (value for value in values if len(value) >= 3 or value.isdigit()),
        key=str.lower,
    )


def _current_instruction_instance_literal_cluster_issues(
    path: Path,
    text: str,
    instruction: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    literals = _instruction_instance_literals(instruction)
    matches = [
        literal
        for literal in literals
        if re.search(
            rf"(?<![A-Za-z0-9]){re.escape(literal)}(?![A-Za-z0-9])",
            text,
            re.IGNORECASE,
        )
    ]
    try:
        tree = ast.parse(text) if path.suffix.lower() == ".py" else None
    except SyntaxError:
        tree = None
    parameterized: list[str] = []
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not any(
                isinstance(target, ast.Name)
                and _INSTANCE_PARAMETER_NAMES.search(target.id)
                for target in targets
            ):
                continue
            value_node = node.value
            if isinstance(value_node, ast.Constant) and isinstance(
                value_node.value, (str, int, float)
            ):
                rendered = str(value_node.value)
                if _stated_by_instruction(rendered, instruction):
                    parameterized.append(rendered)
    evidence_values = list(dict.fromkeys([*matches, *parameterized]))
    if len(evidence_values) < 3:
        return []
    return [
        SkillBoundaryIssue(
            kind="current_instruction_instance_literal_cluster",
            file=str(path.relative_to(skill_root)),
            line=min(_line_for(text, value) for value in evidence_values),
            evidence=(
                "embeds current instruction parameters "
                + ", ".join(repr(value) for value in evidence_values[:8])
                + "; parse them from the current instruction instead"
            )[:240],
        )
    ]


def _literal_number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return -float(node.operand.value)
    return None


def _constant_numeric_expression(node: ast.AST) -> float | None:
    """Safely fold a side-effect-free numeric constant expression.

    This deliberately supports only arithmetic and a few scalar builtins. It
    never evaluates names, attributes, subscripts, comprehensions, or arbitrary
    calls, so expressions derived from runtime evidence remain non-constant.
    """
    literal = _literal_number(node)
    if literal is not None:
        return literal
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _constant_numeric_expression(node.operand)
    if isinstance(node, ast.BinOp):
        left = _constant_numeric_expression(node.left)
        right = _constant_numeric_expression(node.right)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.Div):
                value = left / right
            elif isinstance(node.op, ast.FloorDiv):
                value = left // right
            elif isinstance(node.op, ast.Mod):
                value = left % right
            elif isinstance(node.op, ast.Pow) and abs(right) <= 12:
                value = left**right
            else:
                return None
        except (ArithmeticError, OverflowError, ValueError):
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"abs", "float", "int", "max", "min", "round"}
        and not node.keywords
        and 1 <= len(node.args)
        and (
            node.func.id in {"max", "min"}
            or len(node.args) <= (2 if node.func.id == "round" else 1)
        )
    ):
        values = [_constant_numeric_expression(argument) for argument in node.args]
        if any(value is None for value in values):
            return None
        try:
            if node.func.id == "abs":
                result = abs(values[0])
            elif node.func.id == "float":
                result = float(values[0])
            elif node.func.id == "int":
                result = int(values[0])
            elif node.func.id == "max":
                result = max(values)
            elif node.func.id == "min":
                result = min(values)
            else:
                result = round(values[0], int(values[1])) if len(values) == 2 else round(values[0])
        except (ArithmeticError, OverflowError, ValueError):
            return None
        result = float(result)
        return result if math.isfinite(result) else None
    return None


_UNIT_CONVERSION_FACTORS = {60.0, 1000.0, 1_000_000.0}
_BEST_SCORE_SENTINEL_NAME = re.compile(
    r"(?i)best(?:_[a-z][a-z0-9]*)*_score"
)


def _policy_numeric_literal(node: ast.AST) -> float | None:
    """Find an unstated fixed number hidden inside a policy expression.

    Fully constant expressions are folded. For mixed runtime expressions such
    as ``int(3.0 * sample_rate)``, a non-trivial constant factor is returned;
    ``int(runtime_seconds * sample_rate)`` remains runtime-derived and returns
    ``None``. Common unit-conversion factors are ignored only in mixed
    expressions, while a literal default of the same value is still checked.
    """
    constant = _constant_numeric_expression(node)
    if constant is not None:
        return constant
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"abs", "float", "int", "max", "min", "round"}
    ):
        for argument in node.args:
            value = _policy_numeric_literal(argument)
            if value is not None:
                return value
        return None
    if isinstance(node, (ast.BinOp, ast.UnaryOp)):
        children = (
            [node.operand]
            if isinstance(node, ast.UnaryOp)
            else [node.left, node.right]
        )
        for child in children:
            value = _constant_numeric_expression(child)
            if value is not None and value not in {0.0, 1.0} | _UNIT_CONVERSION_FACTORS:
                return value
        for child in children:
            value = _policy_numeric_literal(child)
            if value is not None:
                return value
    return None


def _assignment_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return set()
    return {
        child.id
        for target in targets
        for child in ast.walk(target)
        if isinstance(child, ast.Name)
    }


def _nearest_ancestor(
    node: ast.AST,
    parent_by_id: Mapping[int, ast.AST],
    kinds: tuple[type[ast.AST], ...],
) -> ast.AST | None:
    current = parent_by_id.get(id(node))
    while current is not None:
        if isinstance(current, kinds):
            return current
        current = parent_by_id.get(id(current))
    return None


def _is_runtime_best_score_sentinel(
    tree: ast.AST,
    node: ast.Assign | ast.AnnAssign,
    name: str,
    value: float,
    parent_by_id: Mapping[int, ast.AST],
) -> bool:
    """Allow only a narrow local argmax/argmin ``best_*score = -1`` sentinel.

    The sentinel must be initialized outside a loop, then updated inside a
    later loop from a non-constant runtime candidate. Every comparison that
    mentions it must be the guard whose body performs such an update. This
    deliberately does not exempt acceptance/rejection cutoffs.
    """
    if value != -1.0 or not _BEST_SCORE_SENTINEL_NAME.fullmatch(name):
        return False
    function = _nearest_ancestor(
        node,
        parent_by_id,
        (ast.FunctionDef, ast.AsyncFunctionDef),
    )
    if function is None:
        return False
    loop_kinds = (ast.For, ast.AsyncFor, ast.While)
    if _nearest_ancestor(node, parent_by_id, loop_kinds) is not None:
        return False

    runtime_updates: list[ast.Assign | ast.AnnAssign] = []
    for candidate in ast.walk(function):
        if candidate is node or not isinstance(candidate, (ast.Assign, ast.AnnAssign)):
            continue
        if _nearest_ancestor(
            candidate,
            parent_by_id,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) is not function:
            continue
        if name not in _assignment_names(candidate):
            continue
        if getattr(candidate, "lineno", 0) <= getattr(node, "lineno", 0):
            continue
        if _nearest_ancestor(candidate, parent_by_id, loop_kinds) is None:
            continue
        candidate_value = candidate.value
        if candidate_value is None or _constant_numeric_expression(candidate_value) is not None:
            continue
        runtime_updates.append(candidate)
    if not runtime_updates:
        return False

    comparisons = [
        candidate
        for candidate in ast.walk(function)
        if isinstance(candidate, ast.Compare)
        and any(
            isinstance(child, ast.Name) and child.id == name
            for child in ast.walk(candidate)
        )
        and _nearest_ancestor(
            candidate,
            parent_by_id,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ) is function
    ]
    if not comparisons:
        return False
    for comparison in comparisons:
        if any(
            _constant_numeric_expression(expression) is not None
            for expression in [comparison.left, *comparison.comparators]
        ):
            return False
        guard = _nearest_ancestor(comparison, parent_by_id, (ast.If,))
        if guard is None or not any(
            child is comparison for child in ast.walk(guard.test)
        ):
            return False
        if _nearest_ancestor(guard, parent_by_id, loop_kinds) is None:
            return False
        guarded_updates = {
            id(child)
            for statement in guard.body
            for child in ast.walk(statement)
            if isinstance(child, (ast.Assign, ast.AnnAssign))
            and name in _assignment_names(child)
        }
        if not any(id(update) in guarded_updates for update in runtime_updates):
            return False
    return True


def _python_literal_issues(
    path: Path,
    text: str,
    instruction: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    allowed_numbers = _instruction_numbers(instruction) | _COMMON_NUMBERS
    issues: list[SkillBoundaryIssue] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [_literal_number(child) for child in node.elts]
            numeric = [value for value in values if value is not None]
            if len(numeric) >= 4 and any(value not in allowed_numbers for value in numeric):
                issues.append(
                    SkillBoundaryIssue(
                        kind="fixed_numeric_sequence",
                        file=str(path.relative_to(skill_root)),
                        line=getattr(node, "lineno", 1),
                        evidence="literal numeric sequence must be derived or configured",
                    )
                )
        elif isinstance(node, ast.Dict):
            numeric = [
                value
                for child in node.values
                if (value := _literal_number(child)) is not None
            ]
            if len(numeric) >= 4 and any(value not in allowed_numbers for value in numeric):
                issues.append(
                    SkillBoundaryIssue(
                        kind="fixed_numeric_table",
                        file=str(path.relative_to(skill_root)),
                        line=getattr(node, "lineno", 1),
                        evidence="literal numeric table must be loaded or derived at runtime",
                    )
                )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            target_names = [target.id for target in targets if isinstance(target, ast.Name)]
            if any(_INSTANCE_ALIAS_NAMES.search(name) for name in target_names):
                literal_strings = {
                    child.value
                    for child in ast.walk(value_node)
                    if isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and len(child.value.strip()) >= 3
                    and not _stated_by_instruction(child.value.strip(), instruction)
                }
                if literal_strings:
                    issues.append(
                        SkillBoundaryIssue(
                            kind="fixed_instance_alias_table",
                            file=str(path.relative_to(skill_root)),
                            line=getattr(node, "lineno", 1),
                            evidence=(
                                "alias/special-case table contains unstated literal values; "
                                "derive aliases from public vocabulary or runtime evidence"
                            ),
                        )
                    )
    return issues


def _spreadsheet_layout_issues(
    path: Path,
    text: str,
    public_contract: str,
    task_dir: Path,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject undeclared cell/range literals only in spreadsheet tasks.

    Short manufacturing, station, model, and protocol identifiers commonly
    have the same lexical shape as an A1 cell address (for example ``X1`` or
    ``ST2``).  Applying this check to every task turns those ordinary CSV/text
    identifiers into false spreadsheet-layout findings and can prevent an
    evolution run from ever reaching its surrogate or GT.  A task is in scope
    when it actually supplies an Excel workbook or its public contract names a
    spreadsheet/workbook/worksheet/Excel artifact.  The latter preserves the
    guard for output-workbook tasks whose template is created at runtime.
    """
    has_workbook_input = any(
        input_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}
        for input_path in current_input_files(task_dir)
    )
    has_public_spreadsheet_contract = bool(
        re.search(
            r"(?i)\b(?:spreadsheet|workbook|worksheet|excel|xlsx|xlsm|xls)\b",
            public_contract,
        )
    )
    if not (has_workbook_input or has_public_spreadsheet_contract):
        return []
    issues: list[SkillBoundaryIssue] = []
    seen: set[str] = set()
    ass_tokens = [
        match.span()
        for pattern in (
            r"(?i)\bV4(?:\.00)?\+?(?:\s+Styles)?(?=$|\s|[\],.;:'\"])",
            r"(?i)&H[0-9A-F]{6,8}",
            r"(?im)^\s*\[(?:Script Info|V4\+ Styles|V4\.00\+ Styles|Events|Fonts|Graphics)\]\s*$",
        )
        for match in re.finditer(pattern, text)
    ]
    for match in _SPREADSHEET_RANGE.finditer(text):
        value = match.group(0)
        if any(start <= match.start() and match.end() <= end for start, end in ass_tokens):
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        source_line = text[line_start:line_end]
        if re.search(
            r"\bre\.(?:compile|findall|finditer|search|match|fullmatch|sub)\s*\(\s*r['\"]",
            source_line,
        ):
            continue
        if value.lower() in public_contract.lower() or value.lower() in seen:
            continue
        seen.add(value.lower())
        issues.append(
            SkillBoundaryIssue(
                kind="undeclared_spreadsheet_layout_literal",
                file=str(path.relative_to(skill_root)),
                line=text.count("\n", 0, match.start()) + 1,
                evidence=(
                    f"embeds spreadsheet address/range {value!r} not declared by the "
                    "instruction; locate labeled regions at runtime"
                ),
            )
        )
    return issues


def _structured_map_runtime_policy_issues(
    path: Path,
    text: str,
    task_dir: Path,
    skill_root: Path,
    public_contract: str,
    current_input_only_symbols: frozenset[str],
) -> list[SkillBoundaryIssue]:
    """Reject map-instance geometry and fixed optimization shortlists.

    Structured map inputs carry their dimensions and wrapping mode at runtime.
    A fixed symbolic rule menu is allowed only when every member is explicitly
    declared by the frozen public instruction/background document and none is a
    current-input-only symbol.  This permits a Skill to compile public domain
    rules into executable procedure without forcing it to read background document at
    runtime, while still rejecting a candidate menu learned from the current
    map.  Ranked search may be bounded, but its bound must be a named
    runtime/configuration budget rather than a hidden fixed slice.

    Evidence intentionally omits the observed value and current categories.
    """
    environment_root = task_dir / "environment"
    has_structured_map = environment_root.is_dir() and any(
        candidate.is_file()
        and candidate.suffix.lower() in _STRUCTURED_MAP_SUFFIXES
        and not any(
            part.lower() in {"doc", "skills", "verifier", ".evolution"}
            for part in candidate.relative_to(environment_root).parts
        )
        for candidate in environment_root.rglob("*")
    )
    if not has_structured_map or path.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    public_lower = public_contract.lower()
    public_normalized = re.sub(r"[^a-z0-9]+", "", public_lower)

    def symbol_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def is_public_symbol(value: str) -> bool:
        return _stated_by_instruction(
            value.strip(),
            public_contract,
            instruction_lower=public_lower,
            instruction_normalized=public_normalized,
        )

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    module_numeric_constants: dict[str, float] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        value = _constant_numeric_expression(statement.value)
        if value is None:
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in targets:
            if isinstance(target, ast.Name):
                module_numeric_constants[target.id] = value

    def assignment_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {
            child.id
            for target in targets
            for child in ast.walk(target)
            if isinstance(child, ast.Name)
        }

    def fixed_scalar(node: ast.AST | None) -> bool:
        return isinstance(node, ast.Constant) and isinstance(
            node.value, (bool, int, float)
        )

    def enclosing_function(node: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        current: ast.AST | None = node
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current
            current = parents.get(current)
        return None

    def fixed_search_bound(node: ast.AST | None, owner: ast.AST) -> float | None:
        value = _constant_numeric_expression(node) if node is not None else None
        if value is not None:
            return value
        if not isinstance(node, ast.Name):
            return None
        if node.id in module_numeric_constants:
            return module_numeric_constants[node.id]
        function = enclosing_function(owner)
        if function is None:
            return None
        positional = [*function.args.posonlyargs, *function.args.args]
        defaults = [None] * (len(positional) - len(function.args.defaults)) + list(
            function.args.defaults
        )
        for argument, default in zip(positional, defaults):
            if argument.arg != node.id or default is None:
                continue
            default_value = _constant_numeric_expression(default)
            if default_value is not None:
                return default_value
            if isinstance(default, ast.Name):
                return module_numeric_constants.get(default.id)
        return None

    issues: list[SkillBoundaryIssue] = []
    fixed_coordinate_nodes: list[ast.List | ast.Tuple] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) == 2:
            coordinate = [_constant_numeric_expression(element) for element in node.elts]
            if (
                all(value is not None and float(value).is_integer() for value in coordinate)
                and not all(value in {-1.0, 0.0, 1.0} for value in coordinate)
            ):
                fixed_coordinate_nodes.append(node)

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = assignment_names(node)
            value_node = node.value
            fixed_geometry = sorted(
                name
                for name in names
                if _STRUCTURED_GEOMETRY_NAME.search(name) and fixed_scalar(value_node)
            )
            if fixed_geometry:
                issues.append(
                    SkillBoundaryIssue(
                        kind="fixed_structured_map_geometry",
                        file=str(path.relative_to(skill_root)),
                        line=getattr(node, "lineno", 1),
                        evidence=(
                            "embeds structured-map geometry/wrapping policy in "
                            + ", ".join(fixed_geometry[:6])
                            + "; parse it from the supplied map metadata at runtime"
                        )[:220],
                    )
                )

            if not any(_STATIC_RULE_OPTIONS_NAME.search(name) for name in names):
                continue
            if not isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
                continue
            strings = [
                element.value
                for element in value_node.elts
                if isinstance(element, ast.Constant)
                and isinstance(element.value, str)
            ]
            symbolic = [
                value
                for value in strings
                if re.fullmatch(r"[A-Z][A-Z0-9_ -]{2,}", value.strip())
            ]
            if len(symbolic) >= 3 and len(symbolic) == len(strings):
                fully_public = all(is_public_symbol(value) for value in symbolic)
                has_current_input_only_symbol = any(
                    symbol_key(value) in current_input_only_symbols
                    for value in symbolic
                )
                if fully_public and not has_current_input_only_symbol:
                    continue
                issues.append(
                    SkillBoundaryIssue(
                        kind="fixed_runtime_rule_vocabulary",
                        file=str(path.relative_to(skill_root)),
                        line=getattr(node, "lineno", 1),
                        evidence=(
                            "embeds a fixed optimization rule/category menu; parse "
                            "the permitted runtime rules and categories from supplied "
                            "public metadata"
                        ),
                    )
                )

        if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.iter, ast.Call):
            if isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                axis_names = {
                    child.id for child in ast.walk(node.target) if isinstance(child, ast.Name)
                }
                fixed_bounds = [
                    _constant_numeric_expression(argument) for argument in node.iter.args
                ]
                if (
                    any(_MAP_AXIS_NAME.search(name) for name in axis_names)
                    and len(fixed_bounds) >= 2
                    and all(value is not None for value in fixed_bounds)
                    and any(abs(value) > 1 for value in fixed_bounds if value is not None)
                ):
                    issues.append(
                        SkillBoundaryIssue(
                            kind="fixed_structured_map_search_window",
                            file=str(path.relative_to(skill_root)),
                            line=getattr(node, "lineno", 1),
                            evidence=(
                                "searches an unstated fixed coordinate window; derive "
                                "the search domain from supplied map metadata and runtime "
                                "validity rules"
                            ),
                        )
                    )

        if not isinstance(node, ast.Subscript) or not isinstance(node.slice, ast.Slice):
            continue
        upper = fixed_search_bound(node.slice.upper, node)
        if upper is None or upper <= 1:
            continue
        collection_names = {
            child.id
            for child in ast.walk(node.value)
            if isinstance(child, ast.Name)
        } | {
            child.attr
            for child in ast.walk(node.value)
            if isinstance(child, ast.Attribute)
        }
        if not any(_RANKED_SEARCH_NAME.search(name) for name in collection_names):
            continue
        current: ast.AST | None = node
        controls_search = False
        while current is not None and not isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            parent = parents.get(current)
            if isinstance(parent, (ast.For, ast.AsyncFor)) and any(
                child is node for child in ast.walk(parent.iter)
            ):
                controls_search = True
                break
            if isinstance(parent, ast.comprehension) and any(
                child is node for child in ast.walk(parent.iter)
            ):
                controls_search = True
                break
            if isinstance(parent, (ast.Assign, ast.AnnAssign)):
                target_nodes = (
                    parent.targets if isinstance(parent, ast.Assign) else [parent.target]
                )
                target_names = {
                    child.id
                    for target in target_nodes
                    for child in ast.walk(target)
                    if isinstance(child, ast.Name)
                }
                if any(_RANKED_SEARCH_NAME.search(name) for name in target_names):
                    controls_search = True
                    break
            current = parent
        if not controls_search:
            continue
        issues.append(
            SkillBoundaryIssue(
                kind="fixed_ranked_search_shortlist",
                file=str(path.relative_to(skill_root)),
                line=getattr(node, "lineno", 1),
                evidence=(
                    "uses an unstated fixed ranked-candidate shortlist; derive the "
                    "search breadth from runtime size or an explicit aggregate budget"
                ),
            )
        )
    if len(fixed_coordinate_nodes) >= 3:
        issues.append(
            SkillBoundaryIssue(
                kind="fixed_structured_map_coordinate_cluster",
                file=str(path.relative_to(skill_root)),
                line=min(getattr(node, "lineno", 1) for node in fixed_coordinate_nodes),
                evidence=(
                    "embeds a cluster of fixed map coordinates; discover candidates "
                    "from the supplied map and runtime rules instead"
                ),
            )
        )
    return issues


def _current_artifact_geometry_calibration_issues(
    path: Path,
    text: str,
    task_dir: Path,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject a media instance's geometry plus remembered camera calibration.

    A reusable helper must inspect the current media and derive its transform;
    a resolution accompanied by several fixed roll/pan/tilt/scale values is a
    high-confidence signature of calibration against the current artifact.
    """
    environment_root = task_dir / "environment"
    media_suffixes = {".mp4", ".mov", ".avi", ".mkv", ".png", ".jpg", ".jpeg"}
    excluded = {"doc", "skills", "verifier", ".evolution"}
    has_current_media = environment_root.is_dir() and any(
        candidate.is_file()
        and candidate.suffix.lower() in media_suffixes
        and not any(
            part.lower() in excluded
            for part in candidate.relative_to(environment_root).parts
        )
        for candidate in environment_root.rglob("*")
    )
    if not has_current_media:
        return []
    geometry_matches = list(
        re.finditer(r"(?<!\d)(?:[1-9]\d{2,4})\s*[xX,]\s*(?:[1-9]\d{2,4})(?!\d)", text)
    )
    try:
        tree = ast.parse(text) if path.suffix.lower() == ".py" else None
    except SyntaxError:
        tree = None
    calibration_names: list[str] = []
    dimension_names: set[str] = set()
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            value = _literal_number(node.value) if node.value is not None else None
            if value is None:
                continue
            dimension_names.update(
                name for name in names if re.search(r"(?i)(?:width|height|frame_w|frame_h)", name)
            )
            calibration_names.extend(
                name for name in names if _CAMERA_CALIBRATION_NAMES.search(name)
            )
    has_geometry = bool(geometry_matches) or len(dimension_names) >= 2
    distinct_calibration = list(dict.fromkeys(calibration_names))
    if not has_geometry or len(distinct_calibration) < 2:
        return []
    first_geometry = geometry_matches[0].group(0) if geometry_matches else ", ".join(sorted(dimension_names))
    return [
        SkillBoundaryIssue(
            kind="current_artifact_geometry_calibration",
            file=str(path.relative_to(skill_root)),
            line=(
                text.count("\n", 0, geometry_matches[0].start()) + 1
                if geometry_matches
                else min(_line_for(text, name) for name in dimension_names)
            ),
            evidence=(
                f"embeds media geometry {first_geometry!r} with fixed calibration "
                + ", ".join(distinct_calibration[:8])
                + "; inspect geometry and derive transforms at runtime"
            )[:240],
        )
    ]


def _current_artifact_names(task_dir: Path) -> set[str]:
    names = {path.name.lower() for path in current_input_files(task_dir)}
    environment_root = task_dir / "environment"
    excluded = {"doc", "skills", "verifier", ".evolution", ".git", "node_modules"}
    if environment_root.is_dir():
        for path in environment_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _ARTIFACT_SUFFIXES:
                continue
            relative = path.relative_to(environment_root)
            if any(part in excluded for part in relative.parts):
                continue
            names.add(path.name.lower())
    return {name for name in names if len(name) >= 5}


def _task_artifact_names(task_dir: Path, instruction: str) -> set[str]:
    """Return current input/output artifact names that code must receive as args."""
    names = _current_artifact_names(task_dir)
    for value in re.findall(
        r"/(?:root|app(?:/environment)?)/[A-Za-z0-9_./-]+",
        instruction,
    ):
        name = Path(value.rstrip("`'\".,;:)" )).name.lower()
        if "." in name:
            names.add(name)
    return {name for name in names if len(name) >= 5}


def _instruction_output_bundle_names(instruction: str) -> set[str]:
    """Return filenames explicitly declared below an instruction output root.

    A reusable bundle builder normally accepts an output directory and then
    creates contract-defined children such as ``index.html`` or
    ``css/style.css``.  Those relative child names are part of the public
    output schema, not observations copied from the current input.  Keep this
    narrow: only absolute instruction paths containing an ``output`` or
    ``outputs`` directory qualify, and the executable Skill must still avoid
    hard-coded absolute paths and parent traversal.
    """
    names: set[str] = set()
    for raw in re.findall(
        r"/(?:root|app(?:/environment)?)/[A-Za-z0-9_./-]+",
        instruction,
    ):
        cleaned = raw.rstrip("`'\".,;:)")
        path = Path(cleaned)
        if not any(part.lower() in {"output", "outputs"} for part in path.parts):
            continue
        if "." in path.name and len(path.name) >= 5:
            names.add(path.name.lower())
    return names


def _python_current_artifact_path_issues(
    path: Path,
    text: str,
    task_dir: Path,
    instruction: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject current artifact paths embedded in executable Skill code.

    A documented invocation may show paths supplied by the instruction, but the
    reusable implementation itself must accept those paths from its caller. A
    helper that embeds the current input/output filename cannot transfer to a
    renamed or unrelated instance even when its computation is otherwise sound.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    artifact_names = _task_artifact_names(task_dir, instruction)
    if not artifact_names:
        return []
    public_output_names = _instruction_output_bundle_names(instruction)
    issues: list[SkillBoundaryIssue] = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        literal = node.value.strip()
        normalized = literal.replace("\\", "/").rstrip("/").lower()
        basename = normalized.rsplit("/", 1)[-1]
        if basename not in artifact_names:
            continue
        relative_parts = normalized.split("/")
        is_public_output_child = (
            basename in public_output_names
            and not normalized.startswith("/")
            and ".." not in relative_parts
        )
        if is_public_output_child:
            continue
        key = (getattr(node, "lineno", 1), basename)
        if key in seen:
            continue
        seen.add(key)
        issues.append(
            SkillBoundaryIssue(
                kind="current_artifact_path_literal",
                file=str(path.relative_to(skill_root)),
                line=getattr(node, "lineno", 1),
                evidence=(
                    f"executable code embeds current artifact {literal!r}; "
                    "accept the runtime path as a caller argument"
                )[:180],
            )
        )
    return issues


def _manifest_undeclared_artifact_issues(
    manifest: Path,
    text: str,
    task_dir: Path,
    instruction: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject current input filenames invented by a SKILL.md example.

    A transfer example may show an input or output path that the public
    instruction explicitly supplies. It must not serialize the rest of the
    current directory listing into an ``expected_files`` list: those names are
    instance observations and make the validator pass only on this task copy.
    """
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    try:
        tree = ast.parse(match.group(1))
    except SyntaxError:
        return []

    current_names = _current_artifact_names(task_dir)
    declared_names = {
        name for name in current_names if _stated_by_instruction(name, instruction)
    }
    undeclared_names = current_names - declared_names
    if not undeclared_names:
        return []

    start_line = text.count("\n", 0, match.start(1)) + 1
    issues: list[SkillBoundaryIssue] = []
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        literal = node.value.strip()
        normalized = literal.replace("\\", "/").rstrip("/").lower()
        basename = normalized.rsplit("/", 1)[-1]
        if basename not in undeclared_names:
            continue
        line = start_line + getattr(node, "lineno", 1) - 1
        key = (line, basename)
        if key in seen:
            continue
        seen.add(key)
        issues.append(
            SkillBoundaryIssue(
                kind="undeclared_current_artifact_manifest_literal",
                file=str(manifest.relative_to(skill_root)),
                line=line,
                evidence=(
                    f"SKILL.md example embeds current input {literal!r} that the "
                    "public instruction did not name; discover runtime inputs"
                )[:180],
            )
        )
    return issues


def _current_source_line_index(task_dir: Path) -> dict[Path, set[str]]:
    """Index distinctive current-repository lines without reading tests/solutions."""
    environment_root = task_dir / "environment"
    if not environment_root.is_dir():
        return {}
    excluded = {
        "doc", "skills", "verifier", ".evolution", ".git", "node_modules",
        ".next", "dist", "build", "target", "__pycache__",
    }
    index: dict[Path, set[str]] = {}
    for source in environment_root.rglob("*"):
        if not source.is_file() or source.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        relative = source.relative_to(environment_root)
        if any(part in excluded for part in relative.parts):
            continue
        try:
            lines = {
                " ".join(line.split())
                for line in source.read_text(encoding="utf-8", errors="replace").splitlines()
                if len(" ".join(line.split())) >= 28
            }
        except OSError:
            continue
        if lines:
            index[source] = lines
    return index


def _current_source_patch_issues(
    skill_file: Path,
    text: str,
    source_index: dict[Path, set[str]],
    task_dir: Path,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    skill_lines = {
        " ".join(line.split())
        for line in text.splitlines()
        if len(" ".join(line.split())) >= 28
    }
    for source, source_lines in source_index.items():
        overlap = sorted(skill_lines & source_lines)
        if len(overlap) < 4:
            continue
        return [
            SkillBoundaryIssue(
                kind="current_source_patch_overlap",
                file=str(skill_file.relative_to(skill_root)),
                line=_line_for(text, overlap[0]),
                evidence=(
                    f"copies {len(overlap)} distinctive lines from "
                    f"{source.relative_to(task_dir)}"
                ),
            )
        ]
    return []


def _repository_history_oracle_issues(
    skill_file: Path,
    text: str,
    skill_root: Path,
    public_contract: str = "",
) -> list[SkillBoundaryIssue]:
    """Reject executable treatment that mines repository history for an answer.

    Benchmark repositories can contain commits outside the checked-out failing
    revision.  Reading those commits is equivalent to consulting a reference
    patch, not diagnosing the public failing state.  Current-tree operations
    such as ``git diff``, ``git status``, and ``git apply`` remain allowed.
    """
    suffix = skill_file.suffix.lower()
    if suffix not in {".py", ".sh"}:
        return []
    matches: list[tuple[int, str]] = []
    historical_diff_operand = re.compile(
        r"(?i)(?:\.\.|[0-9a-f]{7,40}(?=[:.\s]|$)|HEAD(?:~\d*|\^+|@\{)|"
        r"refs/(?:heads|remotes|tags)/|(?:origin|upstream)/[A-Za-z0-9._/-]+)"
    )

    def public_contract_prescribes(command: str) -> bool:
        contract = public_contract.lower()
        operation = f"git {command}"
        for occurrence in re.finditer(re.escape(operation), contract):
            prefix = contract[max(0, occurrence.start() - 80):occurrence.start()]
            if re.search(
                r"(?i)(?:do\s+not|don't|must\s+not|never|avoid|without|"
                r"forbid(?:den)?(?:\s+to)?)\b[^.!?;\n]{0,40}$",
                prefix,
            ):
                continue
            if command != "diff":
                return True
            context = contract[
                max(0, occurrence.start() - 100):occurrence.end() + 140
            ]
            if re.search(
                r"(?i)(?:history|commit|revision|ancestor|parent|HEAD[~^@]|\.\.)",
                context,
            ):
                return True
        return False

    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            git_wrapper_names: set[str] = set()
            for function in (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ):
                wraps_git = any(
                    isinstance(child, (ast.List, ast.Tuple))
                    and child.elts
                    and isinstance(child.elts[0], ast.Constant)
                    and isinstance(child.elts[0].value, str)
                    and child.elts[0].value.lower() == "git"
                    for child in ast.walk(function)
                )
                invokes_process = any(
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr in {"run", "check_call", "check_output", "Popen"}
                    for child in ast.walk(function)
                )
                if wraps_git and invokes_process:
                    git_wrapper_names.add(function.name)

            for node in ast.walk(tree):
                if isinstance(node, (ast.List, ast.Tuple)):
                    values = [
                        child.value
                        if isinstance(child, ast.Constant)
                        and isinstance(child.value, str)
                        else None
                        for child in node.elts
                    ]
                    command = None
                    if values and values[0] and values[0].lower() == "git":
                        index = 1
                        while index < len(values):
                            value = values[index]
                            if value is None:
                                index += 1
                                continue
                            if value in {"-C", "--git-dir", "--work-tree"}:
                                index += 2
                                continue
                            if value.startswith(("--git-dir=", "--work-tree=")):
                                index += 1
                                continue
                            if value.startswith("-"):
                                index += 1
                                continue
                            command = value.lower()
                            break
                    if command in _GIT_HISTORY_ORACLE_COMMANDS:
                        matches.append((getattr(node, "lineno", 1), command))
                    elif command == "diff":
                        argument_text = " ".join(
                            value for value in values if value is not None
                        )
                        if historical_diff_operand.search(argument_text):
                            matches.append((getattr(node, "lineno", 1), command))
                elif isinstance(node, ast.Call):
                    if not isinstance(node.func, ast.Name) or node.func.id not in git_wrapper_names:
                        continue
                    arguments = list(node.args)
                    string_arguments = [
                        argument.value
                        for argument in arguments
                        if isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)
                    ]
                    command = next(
                        (
                            value.lower()
                            for value in string_arguments
                            if value.lower() in _GIT_HISTORY_ORACLE_COMMANDS | {"diff"}
                        ),
                        None,
                    )
                    if command in _GIT_HISTORY_ORACLE_COMMANDS:
                        matches.append((getattr(node, "lineno", 1), command))
                    elif command == "diff":
                        call_text = ast.get_source_segment(text, node) or ""
                        has_history_operand = bool(
                            historical_diff_operand.search(call_text)
                            or any(
                                isinstance(argument, ast.Name)
                                and re.search(
                                    r"(?i)(?:commit|revision|ancestor|parent|old_ref|new_ref)",
                                    argument.id,
                                )
                                for argument in arguments
                            )
                        )
                        if has_history_operand:
                            matches.append((getattr(node, "lineno", 1), command))
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    match = re.search(
                        r"(?i)(?:^|[;&|`$()]\s*)git\s+"
                        r"(log|show|reflog|rev-list|cat-file|format-patch)\b",
                        node.value,
                    )
                    if match:
                        matches.append((getattr(node, "lineno", 1), match.group(1)))
    else:
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = re.search(
                r"(?i)(?:^|[;&|`$()]\s*)git\s+"
                r"(log|show|reflog|rev-list|cat-file|format-patch)\b",
                stripped,
            )
            if match:
                matches.append((line_number, match.group(1)))
                continue
            diff_match = re.search(
                r"(?i)(?:^|[;&|`$()]\s*)git\s+diff\b([^\n;&|]*)",
                stripped,
            )
            if diff_match and historical_diff_operand.search(diff_match.group(1)):
                matches.append((line_number, "diff"))
    if not matches:
        return []
    admissible_matches = [
        item for item in matches if not public_contract_prescribes(item[1])
    ]
    if not admissible_matches:
        return []
    line, command = min(admissible_matches)
    return [
        SkillBoundaryIssue(
            kind="current_repository_history_oracle",
            file=str(skill_file.relative_to(skill_root)),
            line=line,
            evidence=(
                f"executes git {command} to inspect commit history; diagnose from "
                "the checked-out source, public logs, and runtime tests instead"
            ),
        )
    ]


def _fixed_dependency_version_issues(
    skill_file: Path,
    text: str,
    public_contract: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject a baked Maven coordinate/version lookup absent public evidence."""
    if skill_file.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        mapping: dict[str, str] = {}
        for key_node, value_node in zip(node.keys, node.values):
            if (
                isinstance(key_node, ast.Constant)
                and isinstance(key_node.value, str)
                and isinstance(value_node, ast.Constant)
                and isinstance(value_node.value, str)
            ):
                mapping[key_node.value.lower()] = value_node.value
        version = mapping.get("version")
        if (
            not version
            or "groupid" not in mapping
            or "artifactid" not in mapping
            or not re.search(r"\d", version)
            or _stated_by_instruction(version, public_contract)
        ):
            continue
        return [
            SkillBoundaryIssue(
                kind="unjustified_fixed_dependency_version",
                file=str(skill_file.relative_to(skill_root)),
                line=getattr(node, "lineno", 1),
                evidence=(
                    "embeds a fixed Maven dependency version not declared by the "
                    "public contract; derive a compatible version from the current "
                    "project's dependency management and runtime resolution evidence"
                ),
            )
        ]
    return []


def _undeclared_exact_security_policy_replacement_issues(
    skill_file: Path,
    text: str,
    public_contract: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject an undisclosed exact security-policy replacement.

    A current solution can evade source-line and identifier gates by retaining
    only public framework vocabulary while serializing the new replacement
    value (for example, a fixed boolean policy argument) into patch and
    validation code.  Security Skills may discover candidate control points,
    generate alternatives, and behavior-test them, but an exact policy
    assignment not prescribed by the public contract must be derived from
    runtime evidence rather than remembered as the treatment answer.
    """
    if not _SECURITY_SENSITIVE_CONTRACT.search(public_contract):
        return []
    treatment_context = bool(
        _PRESCRIPTIVE_SECURITY_TREATMENT.search(text)
        or re.search(r"(?i)\b(?:re\.sub|write_text|git\s+apply)\b", text)
    )
    if not treatment_context:
        return []
    public_lower = public_contract.lower()
    public_normalized = re.sub(r"[^a-z0-9]+", "", public_lower)
    for match in _EXACT_BOOLEAN_POLICY.finditer(text):
        fragment = match.group(0).strip()
        if _stated_by_instruction(
            fragment,
            public_contract,
            instruction_lower=public_lower,
            instruction_normalized=public_normalized,
        ):
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        line_text = text[line_start:line_end]
        if skill_file.suffix.lower() == ".md" and not (
            _PRESCRIPTIVE_SECURITY_TREATMENT.search(line_text)
            or re.search(r"(?i)\b(?:fix|solution|two[- ]layer|control point)\b", line_text)
        ):
            continue
        return [
            SkillBoundaryIssue(
                kind="undeclared_exact_security_policy_replacement",
                file=str(skill_file.relative_to(skill_root)),
                line=text.count("\n", 0, match.start()) + 1,
                evidence=(
                    f"prescribes exact security-policy replacement {fragment!r} "
                    "that is not declared by the public contract; discover and "
                    "select the control point from runtime source/API evidence, "
                    "then validate exploit and legitimate behavior"
                )[:220],
            )
        ]

    # A fixed policy can be hidden one level behind a function that claims to
    # "derive" it from an API name and then feeds the returned string into a
    # patch template.  That is still a serialized treatment answer unless the
    # Skill actually generates alternatives and selects one by exercising both
    # the attack and a legitimate/control behavior at runtime.  Merely checking
    # that the chosen token appears in source is not behavioral selection.
    if skill_file.suffix.lower() == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None:
            behavior_selected = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Name):
                    call_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                else:
                    continue
                if not re.search(r"(?i)(?:behavior|behaviour).*(?:test|valid)", call_name):
                    continue
                keyword_names = {
                    keyword.arg.lower()
                    for keyword in node.keywords
                    if keyword.arg is not None
                }
                call_source = ast.get_source_segment(text, node) or ""
                has_attack = bool(
                    keyword_names & {"attack", "attacks", "exploit", "malicious"}
                    or re.search(r"(?i)\b(?:attack|exploit|malicious)\b", call_source)
                )
                has_control = bool(
                    keyword_names & {"control", "controls", "legitimate", "benign"}
                    or re.search(r"(?i)\b(?:control|legitimate|benign)\b", call_source)
                )
                if has_attack and has_control:
                    behavior_selected = True
                    break

            if not behavior_selected:
                policy_function = re.compile(
                    r"(?i)(?:allow|deny|enable|disable|input|inject|override|"
                    r"permission|policy|restrict|security|trusted)"
                )
                for function in (
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and policy_function.search(node.name)
                ):
                    for node in ast.walk(function):
                        if not isinstance(node, ast.Return):
                            continue
                        value = node.value
                        fixed_boolean: str | None = None
                        if isinstance(value, ast.Constant) and isinstance(value.value, bool):
                            fixed_boolean = str(value.value).lower()
                        elif (
                            isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                            and value.value.lower() in {"true", "false"}
                        ):
                            fixed_boolean = value.value.lower()
                        if fixed_boolean is None:
                            continue
                        contract_prescribes_boolean = bool(
                            re.search(
                                rf"(?is)\b(?:must|should|required\s+to|by)\s+"
                                rf"(?:set|return|assign|replace|override)\b"
                                rf"[^.!?\n]{{0,140}}\b(?:input|inject|override|"
                                rf"permission|policy|security|trusted)[A-Za-z0-9_.-]*"
                                rf"[^.!?\n]{{0,80}}\b{re.escape(fixed_boolean)}\b",
                                public_contract,
                            )
                            or (
                                function.name.lower() in public_lower
                                and re.search(
                                    rf"(?is){re.escape(function.name)}[^.!?\n]{{0,100}}"
                                    rf"\b{re.escape(fixed_boolean)}\b",
                                    public_contract,
                                )
                            )
                        )
                        if contract_prescribes_boolean:
                            continue
                        return [
                            SkillBoundaryIssue(
                                kind="undeclared_exact_security_policy_replacement",
                                file=str(skill_file.relative_to(skill_root)),
                                line=getattr(node, "lineno", 1),
                                evidence=(
                                    f"returns fixed security-policy literal "
                                    f"{fixed_boolean!r} from {function.name} without "
                                    "runtime attack-plus-control behavior selection; "
                                    "generate candidates and select by effective behavior"
                                )[:220],
                            )
                        ]
    return []


def _resolved_local_string(
    node: ast.AST,
    constants: Mapping[str, str],
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def _distinctive_source_replacement_literal(value: str) -> bool:
    """Identify fixed API/coordinate/XML tokens, not prose or paths."""
    stripped = value.strip()
    if len(stripped) < 8 or stripped.startswith(("/", "./", "../")):
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){2,}", stripped):
        return True
    if re.fullmatch(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)?", stripped):
        return True
    return bool(re.search(r"</?[A-Za-z][A-Za-z0-9_.:-]*(?:\s[^>]*)?>", stripped))


def _undeclared_exact_source_replacement_issues(
    skill_file: Path,
    text: str,
    public_contract: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject fixed old/new source treatments absent the public contract.

    A reusable fixer may parse diagnostics and pass runtime-derived old/new API
    names or dependency coordinates into a mutation helper.  It must not retain
    a benchmark instance's exact migration pair merely because both names are
    public ecosystem vocabulary rather than rare current-source identifiers.
    """
    if skill_file.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    public_lower = public_contract.lower()
    public_normalized = re.sub(r"[^a-z0-9]+", "", public_lower)

    # A fixed old/new answer can be hidden in a nested migration registry and
    # looked up through runtime variables before reaching the mutation helper.
    # The call-site-only check below cannot see through that indirection.  A
    # reusable repair procedure should derive the pair from diagnostics and
    # current project metadata (or load an independently maintained public
    # registry), not carry a benchmark-selected literal registry in its source.
    for assignment in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ):
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        target_names = [target.id for target in targets if isinstance(target, ast.Name)]
        if not any(
            re.search(r"(?i)(?:compat|migrat|relocat|replace|rewrite)", name)
            for name in target_names
        ):
            continue
        value_node = assignment.value
        if not isinstance(value_node, ast.Dict):
            continue
        registry_literals = list(dict.fromkeys(
            child.value
            for child in ast.walk(value_node)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+",
                child.value.strip(),
            )
        ))
        if len(registry_literals) < 2:
            continue
        undeclared = [
            value
            for value in registry_literals
            if not _stated_by_instruction(
                value,
                public_contract,
                instruction_lower=public_lower,
                instruction_normalized=public_normalized,
            )
        ]
        if undeclared:
            return [
                SkillBoundaryIssue(
                    kind="undeclared_exact_source_replacement",
                    file=str(skill_file.relative_to(skill_root)),
                    line=getattr(assignment, "lineno", 1),
                    evidence=(
                        f"embeds a fixed {target_names[0]} API migration registry "
                        "not declared by the public contract; derive the old/new "
                        "pair from runtime diagnostics and project metadata or "
                        "load an independently maintained public registry"
                    )[:220],
                )
            ]

    scopes = [tree, *(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))]
    for scope in scopes:
        constants: dict[str, str] = {}
        for node in ast.walk(scope):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value_node = node.value
            if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value_node.value
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                continue
            if not _EXACT_SOURCE_MUTATION_CALL.search(call_name):
                continue
            resolved = [
                value
                for argument in [*node.args, *(keyword.value for keyword in node.keywords)]
                if (value := _resolved_local_string(argument, constants)) is not None
                and _distinctive_source_replacement_literal(value)
            ]
            resolved = list(dict.fromkeys(resolved))
            if len(resolved) < 2:
                continue
            undeclared = [
                value
                for value in resolved
                if not _stated_by_instruction(
                    value,
                    public_contract,
                    instruction_lower=public_lower,
                    instruction_normalized=public_normalized,
                )
            ]
            if not undeclared:
                continue
            return [
                SkillBoundaryIssue(
                    kind="undeclared_exact_source_replacement",
                    file=str(skill_file.relative_to(skill_root)),
                    line=getattr(node, "lineno", 1),
                    evidence=(
                        f"passes {len(resolved)} fixed API/dependency/XML literals "
                        f"to {call_name} although the complete replacement is not "
                        "declared by the public contract; parse the failing diagnostic "
                        "and derive both sides from runtime source/project metadata"
                    )[:220],
                )
            ]
    return []


def _current_source_target_issues(
    skill_file: Path,
    text: str,
    source_index: dict[Path, set[str]],
    task_dir: Path,
    instruction: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject an undeclared current source target serialized into a Skill.

    Exact-line overlap does not catch a patch generator that names the current
    file and emits new replacement lines.  An evolved procedure may discover a
    source target at runtime, but it must not remember an undeclared filename or
    repository-relative path from the evolution instance.  Filenames explicitly
    supplied by the public instruction remain allowed.
    """
    lower = text.lower()
    normalized_instruction = instruction.lower()
    issues: list[SkillBoundaryIssue] = []
    seen: set[str] = set()
    environment_root = task_dir / "environment"

    for source in source_index:
        relative = source.relative_to(environment_root).as_posix()
        basename = source.name
        candidates = (relative, basename)
        matched = next(
            (
                candidate
                for candidate in candidates
                if len(candidate) >= 8
                and candidate.lower() in lower
                and candidate.lower() not in normalized_instruction
            ),
            None,
        )
        if matched is None or matched.lower() in seen:
            continue
        seen.add(matched.lower())
        issues.append(
            SkillBoundaryIssue(
                kind="undeclared_current_source_target",
                file=str(skill_file.relative_to(skill_root)),
                line=_line_for(text, matched),
                evidence=(
                    f"embeds current source target {matched!r}; discover the "
                    "repair location from runtime diagnostics/source inspection"
                )[:180],
            )
        )
    return issues


def _current_source_identifier_cluster_issues(
    skill_file: Path,
    text: str,
    source_identifiers: Mapping[str, str],
    public_contract: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject rare current-source identifiers copied into a Skill.

    A filename gate misses patch prose such as a private attribute plus the
    exact operation to perform on it.  One highly distinctive private/long
    identifier is sufficient evidence; otherwise require a cluster of at least
    two rare identifiers.  Public instruction/background document terms and generic API
    vocabulary are filtered before this function is called and checked again
    here for defense in depth.
    """
    skill_identifiers = set(_SOURCE_IDENTIFIER.findall(text))
    matches = sorted(
        (
            identifier
            for identifier in skill_identifiers
            if identifier in source_identifiers
            and _distinctive_source_identifier(identifier)
            and not _stated_by_instruction(identifier, public_contract)
        ),
        key=lambda value: (-len(value), value),
    )
    if not matches:
        return []
    highly_distinctive = [
        identifier
        for identifier in matches
        if len(identifier.lstrip("_")) >= 20
        or (identifier.startswith("_") and len(identifier.lstrip("_")) >= 10)
    ]
    mutation_treatment = bool(
        re.search(
            r"(?i)\b(?:re\.sub|replace|write_text|apply_fix|save_diff|"
            r"replacement|fixed\s*=|patch)\b",
            text,
        )
    )
    single_treatment_identifier = mutation_treatment and any(
        "_" in identifier.lstrip("_")
        or re.search(r"[a-z0-9][A-Z]", identifier)
        for identifier in matches
    )
    if len(matches) < 2 and not highly_distinctive and not single_treatment_identifier:
        return []
    evidence_names = matches[:6]
    origins = sorted({source_identifiers[name] for name in evidence_names})
    return [
        SkillBoundaryIssue(
            kind="current_source_identifier_cluster",
            file=str(skill_file.relative_to(skill_root)),
            line=min(_line_for(text, identifier) for identifier in evidence_names),
            evidence=(
                "embeds rare current-source identifier(s) "
                + ", ".join(repr(identifier) for identifier in evidence_names)
                + "; observed in "
                + ", ".join(origins[:3])
                + "; diagnose and discover identifiers at runtime"
            )[:240],
        )
    ]


def _module_public_names(path: Path) -> set[str]:
    """Return names a simple ``from module import name`` can resolve statically."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _module_function_mutates_artifacts(module_path: Path, function_name: str) -> bool:
    """Return whether a local helper call graph performs a concrete write.

    An advertised ``apply_*`` entrypoint that only diagnoses and prints advice
    is not an executable treatment: a fresh agent must then recreate the patch
    manually. Follow calls between functions in the same module so a thin
    public wrapper around a real writer is still accepted.
    """
    module_cache: dict[Path, tuple[ast.Module, dict[str, ast.AST]]] = {}
    mutating_attributes = {
        "write", "writelines", "write_text", "write_bytes", "rename", "replace",
        "move", "copy", "copy2", "copyfile", "unlink", "mkdir", "makedirs",
        "save", "dump", "to_csv", "to_excel", "export",
    }

    def load_module(path: Path) -> tuple[ast.Module, dict[str, ast.AST]] | None:
        if path in module_cache:
            return module_cache[path]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            return None
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        module_cache[path] = (tree, functions)
        return tree, functions

    def mutates(path: Path, name: str, visiting: set[tuple[Path, str]]) -> bool:
        loaded = load_module(path)
        key = (path, name)
        if loaded is None or key in visiting:
            return False
        _, functions = loaded
        if name not in functions:
            return False
        visiting = {*visiting, key}
        function = functions[name]
        imported_targets: dict[str, tuple[Path, str]] = {}
        for node in ast.walk(function):
            if not isinstance(node, ast.ImportFrom) or not node.module or node.level:
                continue
            target_path = path.parent / Path(*node.module.split(".")).with_suffix(".py")
            if not target_path.is_file():
                target_path = path.parent / Path(*node.module.split(".")) / "__init__.py"
            if not target_path.is_file():
                continue
            for alias in node.names:
                if alias.name != "*":
                    imported_targets[alias.asname or alias.name] = (
                        target_path,
                        alias.name,
                    )
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr in mutating_attributes:
                return True
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                mode_node = node.args[1] if len(node.args) >= 2 else next(
                    (keyword.value for keyword in node.keywords if keyword.arg == "mode"),
                    None,
                )
                if (
                    isinstance(mode_node, ast.Constant)
                    and isinstance(mode_node.value, str)
                    and any(marker in mode_node.value for marker in "wax+")
                ):
                    return True
            if isinstance(node.func, ast.Name):
                if mutates(path, node.func.id, visiting):
                    return True
                target = imported_targets.get(node.func.id)
                if target is not None and mutates(target[0], target[1], visiting):
                    return True
        return False

    return mutates(module_path, function_name, set())


def _documented_api_issues(
    manifest: Path,
    text: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Check that the first Python example is callable by a fresh agent.

    This is deliberately static: executing an end-to-end example could mutate the
    task output or make a network request during preflight.
    """
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return [
            SkillBoundaryIssue(
                kind="missing_runnable_example",
                file=str(manifest.relative_to(skill_root)),
                line=1,
                evidence="SKILL.md has no Python invocation example",
            )
        ]
    example = match.group(1)
    start_line = text.count("\n", 0, match.start(1)) + 1
    try:
        tree = ast.parse(example)
    except SyntaxError as exc:
        return [
            SkillBoundaryIssue(
                kind="invalid_runnable_example",
                file=str(manifest.relative_to(skill_root)),
                line=start_line + max(0, (exc.lineno or 1) - 1),
                evidence="first Python example does not parse",
            )
        ]

    issues: list[SkillBoundaryIssue] = []
    imported_names: set[str] = set()
    imported_targets: dict[str, tuple[Path, str]] = {}
    skill_dir = manifest.parent
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module or node.level:
            continue
        imported = {alias.asname or alias.name for alias in node.names if alias.name != "*"}
        imported_names.update(imported)
        module_rel = Path(*node.module.split("."))
        candidates = [
            skill_dir / "scripts" / module_rel.with_suffix(".py"),
            skill_dir / module_rel.with_suffix(".py"),
            skill_dir / "scripts" / module_rel / "__init__.py",
            skill_dir / module_rel / "__init__.py",
        ]
        module_path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if module_path is None:
            continue
        public_names = _module_public_names(module_path)
        for alias in node.names:
            if alias.name == "*" or alias.name in public_names:
                if alias.name != "*":
                    imported_targets[alias.asname or alias.name] = (
                        module_path,
                        alias.name,
                    )
                continue
            issues.append(
                SkillBoundaryIssue(
                    kind="documented_api_missing",
                    file=str(manifest.relative_to(skill_root)),
                    line=start_line + getattr(node, "lineno", 1) - 1,
                    evidence=f"{node.module}.{alias.name} is not defined in {module_path.name}",
                )
            )

    called_imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in imported_names:
            called_imports.add(node.func.id)
    if imported_names and not called_imports:
        issues.append(
            SkillBoundaryIssue(
                kind="documented_api_not_invoked",
                file=str(manifest.relative_to(skill_root)),
                line=start_line,
                evidence="first Python example imports Skill helpers but calls none of them",
            )
        )

    treatment_targets: list[tuple[str, Path, str]] = []
    for called_name in sorted(called_imports):
        target = imported_targets.get(called_name)
        if target is None:
            continue
        module_path, original_name = target
        if not re.search(r"(?i)(?:apply|fix|repair|rewrite|transform|execute|run)", original_name):
            continue
        treatment_targets.append((called_name, module_path, original_name))
    if treatment_targets and not any(
        _module_function_mutates_artifacts(module_path, original_name)
        for _, module_path, original_name in treatment_targets
    ):
        entrypoints = ", ".join(original_name for _, _, original_name in treatment_targets)
        issues.append(
            SkillBoundaryIssue(
                kind="documented_treatment_not_executable",
                file=str(manifest.relative_to(skill_root)),
                line=start_line,
                evidence=(
                    f"documented treatment entrypoint(s) {entrypoints} perform no "
                    "concrete artifact write, directly or through its local call graph; "
                    "fresh evaluation would require manual edits"
                ),
            )
        )

    # A copy-paste runnable transfer example cannot leave the difficult domain
    # configuration for the isolated evaluation agent to invent. This catches
    # patterns such as ``build_config(...)  # caller implements this`` that can
    # pass a surrogate on the evolution artifact but fail fresh transfer.
    defined_names = set(imported_names) | set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            defined_names.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            defined_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined_names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined_names.add(node.id)

    unresolved = sorted(
        {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id not in defined_names
        }
    )
    if unresolved:
        issues.append(
            SkillBoundaryIssue(
                kind="documented_example_unresolved_name",
                file=str(manifest.relative_to(skill_root)),
                line=start_line,
                evidence=(
                    "first Python example leaves names for the fresh agent to implement: "
                    + ", ".join(unresolved[:8])
                ),
            )
        )
    return issues


def _hard_property_qualifier_issues(
    skill_file: Path,
    text: str,
    public_contract: str,
    skill_root: Path,
) -> list[SkillBoundaryIssue]:
    """Reject affirmative output labels without same-entity positive evidence.

    Filtering explicit negative rows does not turn missing or unrelated policy
    text into affirmative evidence.  This static gate therefore requires an
    output qualifier to sit behind a fail-closed three-state classifier
    (positive/negative/unknown), and requires that classifier to consume the
    same runtime entity that is rendered.  The check uses only Skill source and
    the public instruction/background document; it never reads an evaluator or reference
    answer.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    docstring_nodes: set[ast.AST] = set()
    for owner in (tree, *functions.values()):
        body = getattr(owner, "body", ())
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_nodes.add(body[0].value)

    def nearest_function(node: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current
            current = parents.get(current)
        return None

    def output_statement(node: ast.AST) -> ast.AST | None:
        current = parents.get(node)
        while current is not None and not isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if isinstance(current, (ast.Return, ast.Assign, ast.AnnAssign, ast.AugAssign)):
                if isinstance(current, (ast.Assign, ast.AnnAssign)):
                    targets = current.targets if isinstance(current, ast.Assign) else [current.target]
                    target_names = {
                        item.id
                        for target in targets
                        for item in ast.walk(target)
                        if isinstance(item, ast.Name)
                    }
                    if target_names and all(
                        _EVIDENCE_ASSIGNMENT_NAME.search(name) for name in target_names
                    ):
                        return None
                return current
            if isinstance(current, ast.Expr) and isinstance(current.value, ast.Call):
                call_name = ""
                if isinstance(current.value.func, ast.Name):
                    call_name = current.value.func.id
                elif isinstance(current.value.func, ast.Attribute):
                    call_name = current.value.func.attr
                if re.search(r"(?i)(?:write|dump|save|emit|append|update)", call_name):
                    return current
            current = parents.get(current)
        return None

    def local_closure(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
        closure: list[ast.AST] = [function]
        seen = {function.name}
        for _ in range(3):
            added = False
            for owner in tuple(closure):
                for call in ast.walk(owner):
                    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                        continue
                    target = functions.get(call.func.id)
                    if target is not None and target.name not in seen:
                        seen.add(target.name)
                        closure.append(target)
                        added = True
            if not added:
                break
        return closure

    def rejects(block: list[ast.stmt]) -> bool:
        return any(
            isinstance(node, (ast.Raise, ast.Return, ast.Continue, ast.Break))
            for statement in block
            for node in ast.walk(statement)
        )

    def has_positive_guard(
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        qualifier_node: ast.Constant,
    ) -> bool:
        qualifier_line = getattr(qualifier_node, "lineno", 0)
        for node in ast.walk(function):
            if isinstance(node, ast.Assert):
                test_text = ast.get_source_segment(text, node.test) or ""
                if "positive" in test_text.lower() and getattr(node, "lineno", 0) <= qualifier_line:
                    return True
            if not isinstance(node, ast.If):
                continue
            test_text = (ast.get_source_segment(text, node.test) or "").lower()
            if "positive" not in test_text:
                continue
            if any(item is qualifier_node for statement in node.body for item in ast.walk(statement)):
                return True
            fail_closed_comparison = any(
                isinstance(item, (ast.NotEq, ast.IsNot, ast.Not))
                for item in ast.walk(node.test)
            )
            if (
                fail_closed_comparison
                and rejects(node.body)
                and getattr(node, "end_lineno", 0) < qualifier_line
            ):
                return True
        return False

    def names(node: ast.AST) -> set[str]:
        return {
            item.id
            for item in ast.walk(node)
            if isinstance(item, ast.Name)
            and item.id not in {"str", "bool", "True", "False", "None", "self"}
        }

    def same_entity_evidence(
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        statement: ast.AST,
    ) -> bool:
        rendered_names = names(statement)
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                call_name = node.func.attr
            else:
                continue
            if not _EVIDENCE_CALL_NAME.search(call_name):
                continue
            evidence_names = {
                name
                for argument in (*node.args, *(keyword.value for keyword in node.keywords))
                for name in names(argument)
                if not re.search(r"(?i)(?:required|request|friendly|property)", name)
            }
            if rendered_names & evidence_names:
                return True
        return False

    issues: list[SkillBoundaryIssue] = []
    seen_locations: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Constant)
            or not isinstance(node.value, str)
            or node in docstring_nodes
        ):
            continue
        qualifier_match = _HARD_PROPERTY_QUALIFIER.search(node.value)
        if qualifier_match is None:
            continue
        qualifier = qualifier_match.group(0)
        if not _stated_by_instruction(qualifier, public_contract):
            continue
        statement = output_statement(node)
        function = nearest_function(node)
        if statement is None or function is None:
            continue

        closure = local_closure(function)
        closure_text = "\n".join(
            ast.get_source_segment(text, owner) or "" for owner in closure
        ).lower()
        has_three_states = all(
            re.search(rf"\b{state}\b", closure_text)
            for state in ("positive", "negative", "unknown")
        )
        handles_missing = bool(re.search(r"\b(?:none|null|missing|unknown)\b", closure_text))
        has_source_semantics = bool(_EVIDENCE_SOURCE_NAME.search(closure_text))
        safe = (
            has_three_states
            and handles_missing
            and has_source_semantics
            and has_positive_guard(function, node)
            and same_entity_evidence(function, statement)
        )
        if safe:
            continue
        location = (getattr(node, "lineno", 1), qualifier.lower())
        if location in seen_locations:
            continue
        seen_locations.add(location)
        issues.append(
            SkillBoundaryIssue(
                kind="hard_property_positive_evidence_missing",
                file=str(skill_file.relative_to(skill_root)),
                line=getattr(node, "lineno", 1),
                evidence=(
                    "emits an affirmative hard-property qualifier without a "
                    "same-entity, explicit-positive, fail-closed source-evidence "
                    "guard; exclusion of negative records does not make missing or "
                    "unrelated policy text positive"
                ),
            )
        )
    return issues


def audit_evolved_skill_directory(
    skill_root: Path,
    task_dir: Path,
    instruction: str,
    current_source_identifiers: Mapping[str, str] | None = None,
    *,
    allow_fresh_run_source_knowledge: bool = False,
) -> list[SkillBoundaryIssue]:
    """Return high-confidence current-instance/hardcoding issues.

    ``allow_fresh_run_source_knowledge`` is a provenance-scoped exception for
    a genuinely fresh, no-seed evolution run.  A repair agent must be able to
    retain API names and a security-policy choice that it derived by inspecting
    and exercising the *current public checkout during that same run*.  The
    caller is responsible for attesting that no prior evolved Skill was present
    or injected and that repository-history/evaluator commands could not run.

    The exception deliberately covers only the two text-overlap heuristics that
    cannot distinguish same-run learning from a copied seed.  Current input and
    output literals, exact source-line patches, fixed targets, dependency pins,
    repository history, and exact source replacements remain audited below.
    """
    issues: list[SkillBoundaryIssue] = []
    public_contract = _public_contract_text(task_dir, instruction)
    source_repair_contract = bool(
        re.search(
            r"(?is)(?:\b(?:fix|repair|patch|debug|remediat\w*|correct)\w*\b"
            r"[^\n]{0,320}\b(?:source|code(?:base)?|repository|repo|build|"
            r"service|application|vulnerab\w*)\b|"
            r"\b(?:source|code(?:base)?|repository|repo|build|service|"
            r"application|vulnerab\w*)\b[^\n]{0,320}"
            r"\b(?:fix|repair|patch|debug|remediat\w*|correct)\w*\b)",
            public_contract,
        )
    )
    allow_same_run_source_knowledge = (
        allow_fresh_run_source_knowledge and source_repair_contract
    )
    source_index = _current_source_line_index(task_dir)
    identifier_index = _current_source_identifier_index(task_dir, public_contract)
    if current_source_identifiers:
        for identifier, origin in current_source_identifiers.items():
            if (
                _distinctive_source_identifier(identifier)
                and not _stated_by_instruction(identifier, public_contract)
            ):
                identifier_index.setdefault(identifier, origin)
    skill_files: list[tuple[Path, str]] = []
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {
            ".md",
            ".py",
            ".json",
            ".yaml",
            ".yml",
            ".txt",
            ".csv",
        }:
            continue
        skill_files.append(
            (path, path.read_text(encoding="utf-8", errors="replace"))
        )

    input_literals_by_path = _relevant_current_input_literals(
        task_dir,
        tuple(text for _, text in skill_files),
    )
    current_input_only_symbols = {
        re.sub(r"[^a-z0-9]+", "", candidate.lower())
        for input_literals in input_literals_by_path.values()
        for source_kind, value in input_literals
        for candidate in _input_literal_components(source_kind, value)
        if candidate.strip()
        and not _stated_by_instruction(candidate.strip(), public_contract)
    }
    current_input_only_symbols.update(
        re.sub(r"[^a-z0-9]+", "", identifier.lower())
        for identifier in identifier_index
    )
    current_input_only_symbol_keys = frozenset(
        symbol for symbol in current_input_only_symbols if symbol
    )
    current_range_boundaries = _current_input_range_boundaries(task_dir)
    for path, text in skill_files:
        issues.extend(
            _input_overlap_issues(
                path,
                text,
                task_dir,
                instruction,
                skill_root,
                input_literals_by_path,
            )
        )
        issues.extend(
            _current_instruction_instance_literal_cluster_issues(
                path,
                text,
                instruction,
                skill_root,
            )
        )
        issues.extend(
            _current_source_patch_issues(
                path,
                text,
                source_index,
                task_dir,
                skill_root,
            )
        )
        issues.extend(
            _repository_history_oracle_issues(
                path,
                text,
                skill_root,
                public_contract,
            )
        )
        issues.extend(
            _fixed_dependency_version_issues(
                path,
                text,
                public_contract,
                skill_root,
            )
        )
        if not allow_same_run_source_knowledge:
            issues.extend(
                _undeclared_exact_security_policy_replacement_issues(
                    path,
                    text,
                    public_contract,
                    skill_root,
                )
            )
        issues.extend(
            _undeclared_exact_source_replacement_issues(
                path,
                text,
                public_contract,
                skill_root,
            )
        )
        issues.extend(
            _current_source_target_issues(
                path,
                text,
                source_index,
                task_dir,
                instruction,
                skill_root,
            )
        )
        if not allow_same_run_source_knowledge:
            issues.extend(
                _current_source_identifier_cluster_issues(
                    path,
                    text,
                    identifier_index,
                    public_contract,
                    skill_root,
                )
            )
        issues.extend(
            _spreadsheet_layout_issues(
                path,
                text,
                public_contract,
                task_dir,
                skill_root,
            )
        )
        issues.extend(
            _structured_map_runtime_policy_issues(
                path,
                text,
                task_dir,
                skill_root,
                public_contract,
                current_input_only_symbol_keys,
            )
        )
        issues.extend(
            _current_artifact_geometry_calibration_issues(
                path,
                text,
                task_dir,
                skill_root,
            )
        )
        if path.suffix.lower() == ".py":
            issues.extend(
                _hard_property_qualifier_issues(
                    path,
                    text,
                    public_contract,
                    skill_root,
                )
            )
            issues.extend(
                _current_input_range_default_issues(
                    path,
                    text,
                    public_contract,
                    task_dir,
                    skill_root,
                    current_range_boundaries,
                )
            )
            issues.extend(
                _python_literal_issues(
                    path,
                    text,
                    public_contract,
                    skill_root,
                )
            )
            issues.extend(
                _python_current_artifact_path_issues(
                    path,
                    text,
                    task_dir,
                    instruction,
                    skill_root,
                )
            )
        elif path.name == "SKILL.md":
            issues.extend(_documented_api_issues(path, text, skill_root))
            issues.extend(
                _manifest_undeclared_artifact_issues(
                    path,
                    text,
                    task_dir,
                    instruction,
                    skill_root,
                )
            )

    unique: list[SkillBoundaryIssue] = []
    seen: set[SkillBoundaryIssue] = set()
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            unique.append(issue)
    return unique
