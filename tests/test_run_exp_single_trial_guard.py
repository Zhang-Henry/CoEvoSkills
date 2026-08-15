from pathlib import Path

import pytest

import run_exp
from run_exp import claim_single_trial_run


def test_single_trial_guard_claims_a_fresh_jobs_root(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    marker = claim_single_trial_run(jobs_dir, tasks_dir)

    assert marker == jobs_dir / ".single-trial-only.claim"
    payload = marker.read_text(encoding="utf-8")
    assert f"tasks_dir={tasks_dir.resolve()}" in payload


def test_single_trial_guard_rejects_same_root_restart(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    claim_single_trial_run(jobs_dir, tasks_dir)

    with pytest.raises(FileExistsError):
        claim_single_trial_run(jobs_dir, tasks_dir)


def test_single_trial_guard_rejects_an_existing_trial_directory(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (jobs_dir / "prior-job" / "task__trial").mkdir(parents=True)

    with pytest.raises(FileExistsError):
        claim_single_trial_run(jobs_dir, tasks_dir)


def test_mutating_workflow_rejects_bundled_tasks() -> None:
    with pytest.raises(RuntimeError, match="Refusing to mutate"):
        run_exp.guard_bundled_tasks_immutable(run_exp.REPO_ROOT / "tasks")


def test_killed_run_archiver_rejects_bundled_tasks() -> None:
    with pytest.raises(RuntimeError, match="Refusing to mutate"):
        run_exp._archive_killed_run(
            "unused-task", "openai/gpt-5.4", run_exp.REPO_ROOT / "tasks"
        )


def test_mutating_workflow_accepts_prepared_tasks(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared-tasks"
    prepared.mkdir()

    run_exp.guard_bundled_tasks_immutable(prepared)


def test_mutating_workspace_lock_rejects_a_second_process_owner(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_lock = run_exp.acquire_mutable_tasks_lock(workspace)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            run_exp.acquire_mutable_tasks_lock(workspace)
    finally:
        first_lock.close()

    next_lock = run_exp.acquire_mutable_tasks_lock(workspace)
    next_lock.close()


def test_model_result_directories_are_provider_aware() -> None:
    names = {
        run_exp._model_subdir("openai/gpt-5.4"),
        run_exp._model_subdir("vertex_ai/claude-opus-4-6"),
        run_exp._model_subdir("google/gemini-3-flash-preview"),
    }

    assert names == {
        "openai-gpt-5-4",
        "vertex-ai-claude-opus-4-6",
        "google-gemini-3-flash-preview",
    }


def test_public_agent_registry_contains_only_shipped_implementations() -> None:
    assert "skill-evolution" not in run_exp.AGENT_IMPORT_PATHS


def test_custom_agent_import_specs_are_extensible_without_builtin_override() -> None:
    assert run_exp.parse_agent_import_specs(
        ["research-agent=example_agents.research:ResearchAgent"]
    ) == {"research-agent": "example_agents.research:ResearchAgent"}

    with pytest.raises(ValueError, match="cannot replace built-in"):
        run_exp.parse_agent_import_specs(
            ["codex-subscription=example_agents.codex:Replacement"]
        )

    with pytest.raises(ValueError, match="NAME=MODULE:CLASS"):
        run_exp.parse_agent_import_specs(["missing-import-path"])
