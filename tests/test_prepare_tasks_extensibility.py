import sys
from pathlib import Path

import pytest

from scripts.prepare_tasks import (
    TASK_COPY_IGNORE,
    main,
    safe_output,
    select_tasks,
    workspace_output,
)


def write_skill_release(release_root: Path) -> None:
    release_root.mkdir()
    (release_root / "skill_status.tsv").write_text(
        "task\tstatus\tbackground_lineage\n"
        "validated-task\tvalidated_skill_only_full_score\tverified\n"
        "candidate-task\tcandidate_not_finalized\tverified\n",
        encoding="utf-8",
    )
    for task in ("validated-task", "candidate-task"):
        (release_root / "skills" / task).mkdir(parents=True)


def test_new_task_can_enter_evolution_without_a_preexisting_skill(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release-v2"
    (release_root / "background_docs" / "new-task").mkdir(parents=True)

    selected = select_tasks(
        "evolution",
        "new-task",
        "all",
        available={"new-task"},
        release_root=release_root,
    )

    assert selected == ["new-task"]
    assert not (release_root / "skills").exists()
    assert not (release_root / "skill_status.tsv").exists()


def test_evolution_requires_only_the_selected_background_documents(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release-v2"
    (release_root / "background_docs" / "ready-task").mkdir(parents=True)

    with pytest.raises(SystemExit, match="missing-doc-task"):
        select_tasks(
            "evolution",
            "ready-task,missing-doc-task",
            "all",
            available={"ready-task", "missing-doc-task"},
            release_root=release_root,
        )


def test_skill_only_still_requires_release_status_and_skill(
    tmp_path: Path,
) -> None:
    release_root = tmp_path / "release-v2"
    release_root.mkdir()

    with pytest.raises(SystemExit, match="status manifest is missing"):
        select_tasks(
            "skill-only",
            "new-task",
            "all",
            available={"new-task"},
            release_root=release_root,
        )


@pytest.mark.parametrize(
    ("skill_set", "requested", "actual_status"),
    [
        ("validated", "candidate-task", "candidate_not_finalized"),
        ("candidate", "validated-task", "validated_skill_only_full_score"),
    ],
)
def test_explicit_skill_only_tasks_cannot_bypass_selected_skill_set(
    tmp_path: Path,
    skill_set: str,
    requested: str,
    actual_status: str,
) -> None:
    release_root = tmp_path / "release-v2"
    write_skill_release(release_root)

    with pytest.raises(
        SystemExit,
        match=rf"--skill-set {skill_set} excludes.*{requested}.*{actual_status}",
    ):
        select_tasks(
            "skill-only",
            requested,
            skill_set,
            available={"validated-task", "candidate-task"},
            release_root=release_root,
        )


@pytest.mark.parametrize(
    ("skill_set", "requested"),
    [
        ("validated", "validated-task"),
        ("candidate", "candidate-task"),
        ("all", "validated-task,candidate-task"),
    ],
)
def test_explicit_skill_only_tasks_matching_selected_skill_set_are_staged(
    tmp_path: Path,
    skill_set: str,
    requested: str,
) -> None:
    release_root = tmp_path / "release-v2"
    write_skill_release(release_root)

    selected = select_tasks(
        "skill-only",
        requested,
        skill_set,
        available={"validated-task", "candidate-task"},
        release_root=release_root,
    )

    assert selected == sorted(requested.split(","))


def test_rejected_explicit_task_does_not_create_an_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_root = tmp_path / "release-v2"
    write_skill_release(release_root)
    base = tmp_path / "tasks"
    for task in ("validated-task", "candidate-task"):
        task_dir = base / task
        task_dir.mkdir(parents=True)
        (task_dir / "task.toml").write_text("version = '1'\n", encoding="utf-8")
    output = tmp_path / "must-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_tasks.py",
            "--condition",
            "skill-only",
            "--base",
            str(base),
            "--release-root",
            str(release_root),
            "--output",
            str(output),
            "--tasks",
            "candidate-task",
            "--skill-set",
            "validated",
        ],
    )

    with pytest.raises(SystemExit, match="candidate_not_finalized"):
        main()

    assert not output.exists()


def test_run_scoped_workspace_path_and_validation() -> None:
    assert workspace_output("evolution", "paper-v2-r1").parts[-3:] == (
        "workspaces",
        "paper-v2-r1",
        "evolution",
    )
    with pytest.raises(SystemExit, match="run ID"):
        workspace_output("evolution", "../shared")
    with pytest.raises(SystemExit, match="set RUN_ID"):
        workspace_output("evolution", "")


def test_task_staging_ignores_local_python_caches(tmp_path: Path) -> None:
    names = [
        "instruction.md",
        "module.py",
        "module.pyc",
        "module.pyo",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    ]

    ignored = set(TASK_COPY_IGNORE(str(tmp_path), names))

    assert ignored == {
        "module.pyc",
        "module.pyo",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }


def test_output_cannot_overwrite_a_source_or_release_bundle(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tasks"
    release = tmp_path / "release"
    source.mkdir()
    release.mkdir()

    with pytest.raises(SystemExit, match="protected source"):
        safe_output(release / "generated", protected_roots=(source, release))
    with pytest.raises(SystemExit, match="protected source"):
        safe_output(source, protected_roots=(source, release))

    assert safe_output(
        tmp_path / "workspaces" / "run-1",
        protected_roots=(source, release),
    ) == (tmp_path / "workspaces" / "run-1").resolve()
