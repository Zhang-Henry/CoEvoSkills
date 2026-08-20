#!/usr/bin/env python3
"""Stage benchmark tasks for one public CoEvoSkills condition."""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.terminus_agent.evolution.skill_schema import validate_skill_path
from scripts.task_gen.patch_dockerfiles_for_evolution import (
    patch_dockerfile as patch_evolution_dependencies,
)
from scripts.task_gen.patch_python_symlink import patch_dockerfile as patch_python_symlink
from scripts.task_gen.patch_runtime_compatibility import (
    patch_dockerfile as patch_runtime_compatibility,
)


CONDITIONS = {"evolution", "skill-only"}
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TASK_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def safe_output(path: Path, *, protected_roots: tuple[Path, ...] = ()) -> Path:
    resolved = path.expanduser().resolve()
    if resolved in {Path("/"), Path.home().resolve(), ROOT.resolve()}:
        raise SystemExit(f"unsafe output directory: {resolved}")
    for protected_root in protected_roots:
        protected = protected_root.expanduser().resolve()
        if resolved == protected or protected in resolved.parents:
            raise SystemExit(
                f"output directory cannot be inside protected source {protected}: "
                f"{resolved}"
            )
    return resolved


def patch_dockerfile(path: Path, *, doc: bool, skill: bool) -> None:
    if not path.is_file():
        return
    output: list[str] = []
    has_doc = False
    has_skill = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("COPY doc ") or stripped.startswith("# COPY doc "):
            if doc:
                output.append("COPY doc /app/environment/doc")
                has_doc = True
            continue
        if stripped.startswith("COPY skills") or stripped.startswith("# COPY skills"):
            if skill:
                statement = stripped.removeprefix("# ")
                output.append(f"{indent}{statement}")
                has_skill = "/app/environment/skills" in statement or has_skill
            continue
        output.append(line)
    if doc and not has_doc:
        output.extend(["", "# CoEvoSkills background document", "COPY doc /app/environment/doc"])
    if skill and not has_skill:
        output.extend(["", "# CoEvoSkills released Skill", "COPY skills /app/environment/skills"])
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def benchmark_tasks() -> set[str]:
    tasks_root = ROOT / "tasks"
    if not tasks_root.is_dir():
        raise SystemExit(f"bundled benchmark directory is missing: {tasks_root}")
    return {
        path.name
        for path in tasks_root.iterdir()
        if path.is_dir() and (path / "task.toml").is_file()
    }


def skill_statuses(release_root: Path) -> dict[str, str]:
    status_path = release_root / "skill_status.tsv"
    if not status_path.is_file():
        raise SystemExit(f"release status manifest is missing: {status_path}")
    with status_path.open(encoding="utf-8", newline="") as stream:
        return {
            row["task"]: row["status"]
            for row in csv.DictReader(stream, delimiter="\t")
        }


def _requested_tasks(requested: str, available: set[str]) -> set[str]:
    if not requested:
        return set(available)
    selected = {item.strip() for item in requested.split(",") if item.strip()}
    unknown = selected - available
    if unknown:
        raise SystemExit(f"unknown tasks: {sorted(unknown)}")
    return selected


def select_tasks(
    condition: str,
    requested: str,
    skill_set: str,
    *,
    available: set[str],
    release_root: Path,
) -> list[str]:
    if condition == "evolution" and skill_set != "all":
        raise SystemExit("--skill-set applies only to the skill-only condition")

    selected = _requested_tasks(requested, available)
    if condition == "evolution":
        missing_docs = sorted(
            task
            for task in selected
            if not (release_root / "background_docs" / task).is_dir()
        )
        if missing_docs:
            raise SystemExit(
                "background documents are missing for evolution tasks: "
                f"{missing_docs}"
            )
        return sorted(selected)

    statuses = skill_statuses(release_root)
    missing_status = sorted(selected - set(statuses))
    if missing_status:
        raise SystemExit(
            f"release status is missing for Skill-only tasks: {missing_status}"
        )
    if skill_set != "all":
        prefix = "validated_" if skill_set == "validated" else "candidate_"
        if requested:
            mismatched = sorted(
                f"{task} ({statuses[task]})"
                for task in selected
                if not statuses[task].startswith(prefix)
            )
            if mismatched:
                raise SystemExit(
                    f"--skill-set {skill_set} excludes requested Skill-only tasks: "
                    f"{mismatched}"
                )
        else:
            selected = {
                task
                for task, status in statuses.items()
                if task in available and status.startswith(prefix)
            }

    skills_root = release_root / "skills"
    missing_skills = sorted(
        task for task in selected if not (skills_root / task).is_dir()
    )
    if missing_skills:
        raise SystemExit(
            f"released Skills are missing for Skill-only tasks: {missing_skills}"
        )
    return sorted(selected)


def workspace_output(
    condition: str,
    run_id: str,
    workspace_root: Path = ROOT / "workspaces",
) -> Path:
    if not run_id:
        raise SystemExit(
            "set RUN_ID or pass --run-id (or provide an explicit --output directory)"
        )
    if not RUN_ID_RE.fullmatch(run_id):
        raise SystemExit(
            "run ID must start with an alphanumeric character and contain only "
            "letters, numbers, '.', '_' or '-'"
        )
    return workspace_root.expanduser().resolve() / run_id / condition


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, choices=sorted(CONDITIONS))
    parser.add_argument("--base", type=Path, default=ROOT / "tasks")
    parser.add_argument(
        "--release-root",
        type=Path,
        default=ROOT / "artifacts",
        help=(
            "Release bundle containing background_docs/, skills/, and "
            "skill_status.tsv. A custom bundle enables versioned releases."
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path(os.environ.get("WORKSPACE_ROOT", ROOT / "workspaces")),
        help="Parent directory for run-scoped workspaces.",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("RUN_ID", ""),
        help=(
            "Isolated workspace identifier. Defaults to RUN_ID. Required unless "
            "--output is supplied."
        ),
    )
    parser.add_argument("--tasks", default="", help="Optional comma-separated subset.")
    parser.add_argument(
        "--skill-set",
        choices=("all", "validated", "candidate"),
        default="all",
        help=(
            "For Skill-only staging: all Skills, validated Skills, or candidates. "
            "Explicit --tasks must belong to the selected set."
        ),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    base = args.base.expanduser().resolve()
    if not base.is_dir():
        raise SystemExit(f"base task directory does not exist: {base}")
    release_root = args.release_root.expanduser().resolve()
    if not release_root.is_dir():
        raise SystemExit(f"release root does not exist: {release_root}")
    selected = select_tasks(
        args.condition,
        args.tasks,
        args.skill_set,
        available=benchmark_tasks() if base == (ROOT / "tasks").resolve() else {
            path.name
            for path in base.iterdir()
            if path.is_dir() and (path / "task.toml").is_file()
        },
        release_root=release_root,
    )
    output = safe_output(
        args.output
        or workspace_output(args.condition, args.run_id, args.workspace_root),
        protected_roots=(ROOT / "tasks", ROOT / "artifacts", base, release_root),
    )
    if output.exists():
        if not args.force:
            raise SystemExit(f"output already exists: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for task_name in selected:
        source = base / task_name
        destination = output / task_name
        if not (source / "task.toml").is_file():
            raise FileNotFoundError(source / "task.toml")
        shutil.copytree(
            source,
            destination,
            symlinks=True,
            ignore=TASK_COPY_IGNORE,
        )
        environment = destination / "environment"
        doc = environment / "doc"
        skills = environment / "skills"
        for path in (doc, skills, environment / ".evolution", destination / ".evolution"):
            remove_path(path)
        dockerfile = environment / "Dockerfile"
        patch_runtime_compatibility(dockerfile, task_name)

        if args.condition == "evolution":
            shutil.copytree(release_root / "background_docs" / task_name, doc)
        if args.condition == "evolution":
            skills.mkdir(parents=True)
            patch_evolution_dependencies(dockerfile)
            patch_python_symlink(dockerfile)
        elif args.condition == "skill-only":
            shutil.copytree(release_root / "skills" / task_name, skills)
            manifests = sorted(skills.glob("*/SKILL.md"))
            if len(manifests) != 1:
                raise ValueError(f"expected exactly one released Skill for {task_name}")
            issues = validate_skill_path(manifests[0])
            if issues:
                raise ValueError(f"invalid released Skill for {task_name}: {issues}")

        patch_dockerfile(
            dockerfile,
            doc=args.condition == "evolution",
            skill=args.condition == "skill-only",
        )
        if args.condition == "skill-only" and doc.exists():
            raise ValueError(f"background document survived Skill-only staging for {task_name}")

    print(f"Prepared {len(selected)} {args.condition} tasks at {output}")


if __name__ == "__main__":
    main()
