#!/usr/bin/env python3
"""Run isolated CoEvoSkills benchmark conditions and collect their results."""

import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import threading
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, List, Dict, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

# Public runs select the model and Agent explicitly. No provider call is made
# implicitly when the command line omits either value.
MODEL_CONFIGS = []

# Custom agent import paths (for local agent overrides)
AGENT_IMPORT_PATHS = {
    "terminus-2": "libs.terminus_agent.agents.terminus_2.harbor_terminus_2_skills:HarborTerminus2WithSkills",
    "terminus-2-evolution": "libs.terminus_agent.agents.terminus_2.harbor_terminus_2_evolution:HarborTerminus2Evolution",
    "claude-code": "libs.terminus_agent.agents.bedrock_claude_code:BedrockClaudeCode",
    "claude-code-skills": "libs.terminus_agent.agents.claude_code_skills:ClaudeCodeSkills",
    "claude-code-skill-only": "libs.terminus_agent.agents.claude_code_skill_only:ClaudeCodeSkillOnly",
    "codex-skill-only": "libs.terminus_agent.agents.codex_skill_only:CodexSkillOnly",
    "codex-subscription": "libs.terminus_agent.agents.codex_subscription:CodexSubscription",
    "azure-claude-code": "libs.terminus_agent.agents.azure_claude_code:AzureClaudeCode",
}

GT_ORACLE_AGENT_CHOICES = (
    "terminus-2",
    "claude-code",
    "claude-code-skills",
    "claude-code-skill-only",
    "codex",
    "codex-skill-only",
    "codex-subscription",
    "gemini-cli",
)
CUSTOM_AGENT_IMPORTS_ENV = "COEVOSKILLS_CUSTOM_AGENT_IMPORT_PATHS"


def parse_agent_import_specs(specs: list[str] | None) -> dict[str, str]:
    """Parse repeatable NAME=MODULE:CLASS custom Agent registrations."""
    registrations: dict[str, str] = {}
    for spec in specs or []:
        name, separator, import_path = spec.partition("=")
        name = name.strip()
        import_path = import_path.strip()
        if (
            not separator
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
            or ":" not in import_path
            or import_path.startswith(":")
            or import_path.endswith(":")
        ):
            raise ValueError(
                f"invalid Agent import {spec!r}; expected NAME=MODULE:CLASS"
            )
        if name in AGENT_IMPORT_PATHS or name in GT_ORACLE_AGENT_CHOICES:
            raise ValueError(f"custom Agent cannot replace built-in name {name!r}")
        if name in registrations:
            raise ValueError(f"duplicate custom Agent name {name!r}")
        registrations[name] = import_path
    return registrations

# Paths
REPO_ROOT = Path(__file__).resolve().parent
def _refresh_env_from_dotenv():
    """Re-read .env file and update os.environ with any changed values."""
    dotenv_path = REPO_ROOT / ".env"
    if not dotenv_path.exists():
        return
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ[key] = value


def claim_single_trial_run(output_root: Path, tasks_dir: Path) -> Path:
    """Atomically claim an output root for one runner invocation.

    Fresh no-seed experiments must never silently reuse the same task, Skill,
    state, and jobs roots after a terminal Harbor run.  Opening the marker in
    exclusive-create mode makes a second invocation fail before it can archive
    or inherit any agent-created state.
    """
    output_root.mkdir(parents=True, exist_ok=True)
    marker = output_root / ".single-trial-only.claim"
    if marker.exists() or any(path.is_dir() for path in output_root.iterdir()):
        raise FileExistsError(str(marker))
    with marker.open("x", encoding="utf-8") as claim_file:
        claim_file.write(f"claimed_at={datetime.now().isoformat()}\n")
        claim_file.write(f"tasks_dir={tasks_dir.resolve()}\n")
    return marker


def generate_jobs_dir_name(model: str, agent: str, experimenter: Optional[str] = None, difficulty: Optional[str] = None) -> str:
    """Generate a jobs directory name with precise timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    model_short = model.split("/")[-1].replace("-preview", "").replace("-", "").replace(":", "")[:20]
    parts = [timestamp, model_short, agent]
    if difficulty:
        parts.append(difficulty)
    if experimenter:
        parts.append(experimenter)
    return "-".join(parts)

# Keep every generated artifact below one user-selectable output root.
_configured_output_root = os.environ.get(
    "COEVOSKILLS_OUTPUT_DIR", str(REPO_ROOT / "outputs")
)
OUTPUT_ROOT = Path(_configured_output_root).expanduser().resolve()

# Default jobs dir (can be overridden by --jobs-dir)
JOBS_DIR = OUTPUT_ROOT / "jobs"
TASKS_DIR = REPO_ROOT / "tasks"
EXPERIMENTS_DIR = OUTPUT_ROOT / "results"
TRAJECTORIES_DIR = OUTPUT_ROOT / "jobs"

BASELINE_RESULTS_COLUMNS = [
    "experiment_id", "task", "model", "agent", "tasks_dir",
    "tests_passed", "tests_total", "accuracy", "reward",
    "started_at", "duration_sec",
]

EVOLUTION_RESULTS_COLUMNS = [
    "experiment_id", "task", "agent", "condition",
    "tests_passed", "tests_total", "accuracy", "reward",
    "initial_gt_accuracy", "final_gt_accuracy", "max_gt_accuracy",
    "exit_reason", "skills_created", "started_at", "duration_sec", "model",
]


def _model_subdir(model: str) -> str:
    """Return a stable, provider-aware result subdirectory for a model."""
    normalized = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    return normalized or "unknown-model"


def _model_result_dirs() -> list[Path]:
    """Return every existing model result directory, including legacy runs."""
    if not EXPERIMENTS_DIR.is_dir():
        return []
    return sorted(path for path in EXPERIMENTS_DIR.iterdir() if path.is_dir())


def guard_bundled_tasks_immutable(tasks_dir: Path) -> None:
    """Reject workflows that can write generated state into bundled tasks."""
    if tasks_dir.expanduser().resolve() == (REPO_ROOT / "tasks").resolve():
        raise RuntimeError(
            "Refusing to mutate the bundled tasks directory. Run "
            "scripts/prepare_tasks.py and pass its workspace output with --tasks-dir."
        )


def acquire_mutable_tasks_lock(tasks_dir: Path):
    """Exclusively lock a mutable task workspace for this process lifetime."""
    resolved = tasks_dir.expanduser().resolve()
    lock_path = resolved / ".coevoskills-workspace.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        holder = handle.read().strip() or "another active process"
        handle.close()
        raise RuntimeError(
            f"Task workspace is already in use: {resolved} ({holder})"
        ) from exc
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()}\nstarted_at={datetime.now().isoformat()}\n")
    handle.flush()
    return handle


def _safe_int(val) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _evolved_skill_names_on_disk(tasks_dir: str, task: str) -> set[str]:
    """Return completed evolved Skill packages imported into a staged task."""
    if not tasks_dir or not task:
        return set()
    skills_dir = Path(tasks_dir) / task / "environment" / "skills"
    if not skills_dir.is_dir():
        return set()
    return {
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir()
        and path.name.startswith("evo-")
        and (path / "SKILL.md").is_file()
    }


def detect_condition(tasks_dir: Optional[str], agent: str) -> str:
    """Detect the two public experimental conditions."""
    if tasks_dir:
        normalized = str(tasks_dir).lower().replace("_", "-")
        if "skill-only" in normalized:
            return "skill_only"
        if "evolution" in normalized:
            return "evolution_background"
    if "skill-only" in agent or agent == "codex-subscription":
        return "skill_only"
    if "evolution" in agent:
        return "evolution_background"
    return "baseline"


def make_experiment_id(started_at: Optional[str], task: str = "") -> str:
    """Generate a compact experiment_id: MMdd_HHMMSS_taskhash."""
    ts = "unknown"
    if started_at:
        try:
            dt = datetime.fromisoformat(started_at)
            ts = dt.strftime("%m/%d/%H-%M-%S")
        except (ValueError, TypeError):
            pass
    task_hash = hashlib.md5((task or "").encode()).hexdigest()[:4]
    return f"{ts}_{task_hash}"


def _find_evolution_log(job_name: str) -> Optional[Path]:
    """Search trajectories directory for evolution_run_log.json matching job_name."""
    if not TRAJECTORIES_DIR.exists():
        return None
    for session_dir in TRAJECTORIES_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        job_dir = session_dir / job_name
        if not job_dir.exists():
            continue
        for trial in job_dir.iterdir():
            if trial.is_dir() and "__" in trial.name:
                log_path = trial / "agent" / "evolution_run_log.json"
                if log_path.exists():
                    return log_path
    return None


def _load_existing_result_ids() -> set:
    """Load existing experiment_ids from all model-specific result CSVs."""
    ids: set = set()
    for subdir_path in _model_result_dirs():
        for csv_name in ["baseline_results.csv", "evolution_results.csv", "evo_skills_results.csv"]:
            csv_path = subdir_path / csv_name
            if not csv_path.exists():
                continue
            with open(csv_path, newline="") as f:
                for row in csv.DictReader(f):
                    eid = row.get("experiment_id", "")
                    if eid:
                        ids.add(eid)
    return ids


def _append_result_row(result_row: dict):
    """Append a single result row to the appropriate model-specific CSV."""
    subdir = _model_subdir(result_row.get("model", ""))
    condition = result_row.get("condition", "")

    if condition == "evo_skills":
        filename, columns = "evo_skills_results.csv", BASELINE_RESULTS_COLUMNS
    elif condition.startswith("evolution"):
        filename, columns = "evolution_results.csv", EVOLUTION_RESULTS_COLUMNS
    else:
        filename, columns = "baseline_results.csv", BASELINE_RESULTS_COLUMNS

    subdir_path = EXPERIMENTS_DIR / subdir
    subdir_path.mkdir(exist_ok=True)
    csv_path = subdir_path / filename
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(result_row)


def record_run_result(csv_row: dict):
    """Process a completed run and write to model-specific CSV. Called after each task finishes."""
    task = csv_row.get("task") or ""
    model = csv_row.get("model") or ""
    agent = csv_row.get("agent") or ""
    started_at = csv_row.get("started_at") or ""
    tasks_dir_val = csv_row.get("tasks_dir") or ""

    experiment_id = make_experiment_id(started_at, task)

    # Skip if already recorded (check per-task CSV)
    subdir = _model_subdir(model)
    tasks_dir_name = Path(tasks_dir_val).name if tasks_dir_val else "tasks"
    task_csv = EXPERIMENTS_DIR / subdir / tasks_dir_name / task / "results.csv"
    if task_csv.exists():
        try:
            with open(task_csv, newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("experiment_id") == experiment_id:
                        return
        except OSError:
            pass

    condition = detect_condition(tasks_dir_val, agent)
    tests_passed = _safe_int(csv_row.get("tests_passed"))
    tests_total = _safe_int(csv_row.get("tests_total"))
    accuracy = tests_passed / tests_total if tests_total and tests_total > 0 else None
    reward = _safe_float(csv_row.get("reward"))

    result_row = {
        "experiment_id": experiment_id,
        "task": task,
        "model": model,
        "agent": agent,
        "tasks_dir": tasks_dir_val,
        "condition": condition,
        "tests_passed": tests_passed if tests_passed is not None else "",
        "tests_total": tests_total if tests_total is not None else "",
        "accuracy": f"{accuracy:.4f}" if accuracy is not None else "",
        "reward": reward if reward is not None else "",
        "initial_gt_accuracy": "",
        "final_gt_accuracy": "",
        "max_gt_accuracy": "",
        "exit_reason": "",
        "skills_created": "",
        "started_at": started_at,
        "duration_sec": csv_row.get("duration_sec", ""),
    }

    # Enrich with evolution log data if available
    if "evolution" in agent:
        all_evo = _evolved_skill_names_on_disk(tasks_dir_val, task)
        job_name = csv_row.get("job_name") or ""
        log_path = _find_evolution_log(job_name)
        if log_path:
            try:
                log = json.loads(log_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log = None

            if log:
                interventions = log.get("intervention_history", [])
                timing = log.get("timing", {})

                gt_accuracies = []
                for interv in interventions:
                    gt = interv.get("gt_result") or {}
                    gt_acc = gt.get("pass_rate")
                    if gt_acc is not None:
                        gt_accuracies.append(gt_acc)

                result_row["exit_reason"] = timing.get("exit_reason", "")
                if gt_accuracies:
                    result_row["initial_gt_accuracy"] = f"{gt_accuracies[0]:.4f}"
                    result_row["final_gt_accuracy"] = f"{gt_accuracies[-1]:.4f}"
                    result_row["max_gt_accuracy"] = f"{max(gt_accuracies):.4f}"

                execution = log.get("execution", {})
                loaded_skills = execution.get("skills_loaded_by_agent", [])
                evo_skills = [s for s in loaded_skills if s.startswith("evo-")]
                created_skills = execution.get("skills_created_in_container", [])
                all_evo.update(evo_skills)
                all_evo.update(
                    s for s in created_skills if s.startswith("evo-")
                )
        result_row["skills_created"] = ",".join(sorted(all_evo))

    # Write to per-task structured directory (new primary record)
    run_dir = _resolve_run_dir(model, tasks_dir_val, task, started_at)
    _write_result_summary(run_dir, result_row)
    _append_to_task_csv(model, tasks_dir_val, task, result_row)


def _make_run_dir_name(started_at: str) -> str:
    """Convert ISO timestamp to dir name: '20260311T060354'."""
    try:
        dt = datetime.fromisoformat(started_at)
        return dt.strftime("%Y%m%dT%H%M%S")
    except (ValueError, TypeError):
        return datetime.now().strftime("%Y%m%dT%H%M%S")


def _resolve_run_dir(model: str, tasks_dir: str, task: str, started_at: str) -> Path:
    """Return: experiments/{model_subdir}/{tasks_dir_basename}/{task}/{timestamp}/"""
    subdir = _model_subdir(model)
    tasks_dir_name = Path(tasks_dir).name if tasks_dir else "tasks"
    run_name = _make_run_dir_name(started_at)
    run_dir = EXPERIMENTS_DIR / subdir / tasks_dir_name / task / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _copy_run_artifacts(run_dir: Path, job_name: str, tasks_dir: str, task: str) -> None:
    """Copy evolution_run_log.json, evolution_report.md, skills/evo-*, verifier/ into run_dir.

    Sources:
    - outputs/jobs/.../job_name/*/agent/ → logs
    - {tasks_dir}/{task}/environment/skills/evo-* → skills snapshot
    - {tasks_dir}/{task}/environment/verifier/ → verifier scripts
    """
    # 1. Copy logs from trajectories
    log_path = _find_evolution_log(job_name)
    if log_path:
        agent_dir = log_path.parent  # .../agent/
        trial_dir = agent_dir.parent  # .../<task>__<hash>/
        for fname in ["evolution_run_log.json", "evolution_report.md"]:
            # Check both trial_dir and agent_dir (location varies)
            for src_dir in [trial_dir, agent_dir]:
                src = src_dir / fname
                if src.exists():
                    shutil.copy2(src, run_dir / fname)
                    break

    # 2. Copy evolved skills snapshot
    task_env = Path(tasks_dir) / task / "environment"
    skills_dir = task_env / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir() and skill_dir.name.startswith("evo-"):
                dst = run_dir / "skills" / skill_dir.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(skill_dir, dst)

    # 3. Copy verifier scripts
    verifier_dir = task_env / "verifier"
    if verifier_dir.exists():
        gen_scripts = verifier_dir / "generated_scripts"
        if gen_scripts.exists():
            dst = run_dir / "verifier" / "generated_scripts"
            dst.mkdir(parents=True, exist_ok=True)
            for script in gen_scripts.iterdir():
                if script.is_file():
                    shutil.copy2(script, dst / script.name)


def _write_result_summary(run_dir: Path, result_row: dict) -> None:
    """Write compact result_summary.json."""
    summary = {
        "experiment_id": result_row.get("experiment_id", ""),
        "task": result_row.get("task", ""),
        "model": result_row.get("model", ""),
        "agent": result_row.get("agent", ""),
        "condition": result_row.get("condition", ""),
        "tests_passed": result_row.get("tests_passed", ""),
        "tests_total": result_row.get("tests_total", ""),
        "accuracy": result_row.get("accuracy", ""),
        "reward": result_row.get("reward", ""),
        "exit_reason": result_row.get("exit_reason", ""),
        "skills_created": result_row.get("skills_created", ""),
        "initial_gt_accuracy": result_row.get("initial_gt_accuracy", ""),
        "final_gt_accuracy": result_row.get("final_gt_accuracy", ""),
        "max_gt_accuracy": result_row.get("max_gt_accuracy", ""),
        "started_at": result_row.get("started_at", ""),
        "duration_sec": result_row.get("duration_sec", ""),
    }
    summary_path = run_dir / "result_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


TASK_CSV_COLUMNS = [
    "experiment_id", "task", "model", "agent", "condition",
    "tests_passed", "tests_total", "accuracy", "reward",
    "initial_gt_accuracy", "final_gt_accuracy", "max_gt_accuracy",
    "exit_reason", "skills_created", "started_at", "duration_sec",
]


def _append_to_task_csv(model: str, tasks_dir: str, task: str, result_row: dict) -> None:
    """Append row to experiments/{model_subdir}/{tasks_dir_basename}/{task}/results.csv"""
    subdir = _model_subdir(model)
    tasks_dir_name = Path(tasks_dir).name if tasks_dir else "tasks"
    task_dir = EXPERIMENTS_DIR / subdir / tasks_dir_name / task
    task_dir.mkdir(parents=True, exist_ok=True)
    csv_path = task_dir / "results.csv"
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TASK_CSV_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(result_row)


# ============================================================================
# DIFFICULTY FILTERING
# ============================================================================

_tasks_metadata_cache: dict[str, str] | None = None


def load_tasks_metadata() -> dict[str, str]:
    """Load task difficulty values directly from each task.toml file."""
    global _tasks_metadata_cache
    if _tasks_metadata_cache is not None:
        return _tasks_metadata_cache

    metadata: dict[str, str] = {}
    for task_dir in sorted(TASKS_DIR.iterdir()) if TASKS_DIR.exists() else []:
        task_toml = task_dir / "task.toml"
        if not task_dir.is_dir() or not task_toml.exists():
            continue
        try:
            with task_toml.open("rb") as f:
                config = tomllib.load(f)
            difficulty = config.get("metadata", {}).get("difficulty")
            if difficulty:
                metadata[task_dir.name] = str(difficulty)
        except (OSError, tomllib.TOMLDecodeError) as e:
            print(f"Warning: could not read {task_toml}: {e}")

    _tasks_metadata_cache = metadata
    return metadata


def filter_tasks_by_difficulty(all_tasks: List[str], difficulty: str) -> List[str]:
    """Filter tasks by difficulty level."""
    if difficulty == "all":
        return all_tasks

    tasks_metadata = load_tasks_metadata()
    if not tasks_metadata:
        print("Warning: No metadata available, returning all tasks")
        return all_tasks

    filtered_tasks = [
        task for task in all_tasks
        if tasks_metadata.get(task) == difficulty
    ]

    if not filtered_tasks:
        print(f"Warning: No tasks found for difficulty '{difficulty}'")
        print(f"Available difficulties: {sorted(set(tasks_metadata.values()))}")

    return filtered_tasks


def get_task_difficulty(task_id: str) -> str:
    """Get the difficulty level for a specific task."""
    tasks_metadata = load_tasks_metadata()
    return tasks_metadata.get(task_id, "unknown")


# ============================================================================
# CSV TRACKING UTILITIES
# ============================================================================

def load_existing_runs() -> List[dict]:
    """Load existing runs from model-specific evolution_results.csv files."""
    runs = []
    for subdir_path in _model_result_dirs():
        evo_csv = subdir_path / "evolution_results.csv"
        if evo_csv.exists():
            with open(evo_csv, "r", newline="") as f:
                for row in csv.DictReader(f):
                    runs.append(row)
        baseline_csv = subdir_path / "baseline_results.csv"
        if baseline_csv.exists():
            with open(baseline_csv, "r", newline="") as f:
                for row in csv.DictReader(f):
                    runs.append(row)
    return runs


def get_next_run_index(model: str, agent: str, existing_runs: List[dict]) -> int:
    """Get the next run index for a given model+agent combination."""
    count = sum(1 for run in existing_runs if run.get("model") == model and run.get("agent") == agent)
    return count + 1



def _extract_gt_oracle_from_log(job_folder: str) -> dict:
    """Extract gt_oracle_result from evolution_run_log.json if present."""
    job_path = Path(job_folder)
    if not job_path.is_absolute():
        job_path = JOBS_DIR / job_folder
    if not job_path.exists():
        return {}
    try:
        for item in job_path.iterdir():
            if item.is_dir() and "__" in item.name:
                log_path = item / "agent" / "evolution_run_log.json"
                if log_path.exists():
                    try:
                        log = json.loads(log_path.read_text(encoding="utf-8"))
                        return log.get("gt_oracle_result") or {}
                    except (json.JSONDecodeError, KeyError):
                        pass
    except OSError:
        pass
    return {}


def _print_evolution_summary(job_folder: str) -> None:
    """Print a compact intervention summary from evolution_run_log.json."""
    job_path = Path(job_folder)
    if not job_path.is_absolute():
        job_path = JOBS_DIR / job_folder
    if not job_path.exists():
        return
    try:
        log_data = None
        for item in job_path.iterdir():
            if item.is_dir() and "__" in item.name:
                log_path = item / "agent" / "evolution_run_log.json"
                if log_path.exists():
                    log_data = json.loads(log_path.read_text(encoding="utf-8"))
                    break
        if not log_data:
            return

        interventions = log_data.get("interventions", [])
        exit_reason = log_data.get("exit_reason", "unknown")
        if not interventions:
            return

        print(f"    Evolution: {len(interventions)} interventions, exit={exit_reason}")
        best_gt_rate = 0.0
        best_gt_iteration = 0
        last_gt_failures: list[str] = []
        for i, iv in enumerate(interventions, 1):
            trigger = iv.get("trigger", "?")
            surr = iv.get("surrogate_result") or {}
            surr_rate = surr.get("pass_rate")
            surr_str = f"surr={surr_rate:.0%}" if surr_rate is not None else "no-surr"

            gt = iv.get("gt_result") or {}
            if gt:
                gt_rate = gt.get("pass_rate")
                gt_str = f"gt={gt_rate:.0%}" if gt_rate is not None else "gt=err"
                # Track best and last failures for diagnosis
                if gt_rate is not None and gt_rate > best_gt_rate:
                    best_gt_rate = gt_rate
                    best_gt_iteration = i
                if gt_rate is not None and gt_rate < 1.0:
                    last_gt_failures = [
                        d.get("name", "?") for d in gt.get("test_details", [])
                        if d.get("status") in ("FAILED", "ERROR")
                    ]
            else:
                gt_str = "no-gt"

            print(f"      #{i}: {trigger} | {surr_str} | {gt_str}")

        # Print best GT snapshot and last failing tests for quick diagnosis
        if best_gt_iteration > 0:
            print(f"    Best GT: {best_gt_rate:.0%} at iteration #{best_gt_iteration}")
        if last_gt_failures:
            print(f"    Last GT failures: {', '.join(last_gt_failures[:5])}")
    except Exception:
        pass


def check_task_completion(job_folder: str) -> dict:
    """
    Check if a task finished normally by examining verifier outputs.

    Checks multiple indicators of completion:
    1. ctrf.json or ctrf-report.json in verifier folder (with test results)
    2. reward.txt in verifier folder (with numeric value)
    3. result.json in trial folder (with numeric reward)

    A task is considered finished ONLY if we have a concrete reward value (not None).

    Returns dict with:
        - finished_normally: bool - True if we have a concrete reward value
        - all_tests_counted: bool - True if passed + failed == tests
        - tests_total, tests_passed, tests_failed: int counts
        - reward: float or None
    """
    result = {
        "finished_normally": False,
        "all_tests_counted": False,
        "tests_total": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "reward": None,
        "reward_partial": None,
        "reward_partial_cases": None,
    }

    job_path = Path(job_folder)
    if not job_path.is_absolute():
        job_path = JOBS_DIR / job_folder
    if not job_path.exists():
        return result

    # Find trial directory (contains __ in name)
    trial_dir = None
    for item in job_path.iterdir():
        if item.is_dir() and "__" in item.name:
            trial_dir = item
            break

    if not trial_dir:
        return result

    verifier_dir = trial_dir / "verifier"

    # Check for ctrf.json or ctrf-report.json in verifier folder
    ctrf_path = None
    for ctrf_name in ["ctrf.json", "ctrf-report.json"]:
        candidate = verifier_dir / ctrf_name
        if candidate.exists():
            ctrf_path = candidate
            break

    # Primary: parse test-stdout.txt for accurate per-case counts
    # (pytest-json-ctrf folds parametrized tests into single entries, undercounting)
    test_stdout_path = verifier_dir / "test-stdout.txt"
    if test_stdout_path.exists():
        try:
            stdout_text = test_stdout_path.read_text()
            # Parse pytest summary line, e.g. "11 failed, 12 passed, 3 skipped in 0.44s"
            # Use findall + take last match: some tasks have nested pytest runs in stdout
            all_matches = re.findall(r"=+ ([\d\w, ]+) in [\d.]+s.*?=+", stdout_text)
            summary_match = all_matches[-1] if all_matches else None
            if summary_match:
                summary_str = summary_match  # findall returns the captured group directly
                p = re.search(r"(\d+) passed", summary_str)
                f = re.search(r"(\d+) failed", summary_str)
                e = re.search(r"(\d+) error", summary_str)
                n_passed = int(p.group(1)) if p else 0
                n_failed = int(f.group(1)) if f else 0
                n_error = int(e.group(1)) if e else 0
                result["tests_total"] = n_passed + n_failed + n_error  # skip not counted
                result["tests_passed"] = n_passed
                result["tests_failed"] = n_failed + n_error
                result["all_tests_counted"] = True

            # Some benchmark verifiers are custom scripts rather than pytest and
            # report their case counts as "FINAL SCORE: X/Y = Z".
            if result["tests_total"] == 0:
                final_score_matches = re.findall(
                    r"FINAL SCORE:\s*(\d+)\s*/\s*(\d+)",
                    stdout_text,
                    flags=re.IGNORECASE,
                )
                if final_score_matches:
                    passed_text, total_text = final_score_matches[-1]
                    n_passed = int(passed_text)
                    n_total = int(total_text)
                    result["tests_total"] = n_total
                    result["tests_passed"] = n_passed
                    result["tests_failed"] = max(0, n_total - n_passed)
                    result["all_tests_counted"] = True

            # Custom non-pytest verifier summary used by tasks such as the
            # crystallographic Wyckoff benchmark.
            if result["tests_total"] == 0:
                total_matches = re.findall(
                    r"^\s*Total tests:\s*(\d+)\s*$",
                    stdout_text,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                passed_matches = re.findall(
                    r"^\s*Passed:\s*(\d+)\s*$",
                    stdout_text,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                failed_matches = re.findall(
                    r"^\s*Failed:\s*(\d+)\s*$",
                    stdout_text,
                    flags=re.IGNORECASE | re.MULTILINE,
                )
                if total_matches and passed_matches:
                    n_total = int(total_matches[-1])
                    n_passed = int(passed_matches[-1])
                    n_failed = (
                        int(failed_matches[-1])
                        if failed_matches
                        else max(0, n_total - n_passed)
                    )
                    if n_total > 0 and n_passed + n_failed <= n_total:
                        result["tests_total"] = n_total
                        result["tests_passed"] = n_passed
                        result["tests_failed"] = n_failed
                        result["all_tests_counted"] = True
        except IOError:
            pass

    # Fallback: use ctrf.json if test-stdout.txt unavailable or unparseable
    if result["tests_total"] == 0 and ctrf_path:
        try:
            with open(ctrf_path) as f:
                ctrf = json.load(f)

            summary = ctrf.get("results", {}).get("summary", {})
            tests_passed = summary.get("passed", 0)
            tests_failed = summary.get("failed", 0)
            tests_total = tests_passed + tests_failed  # skip not counted

            result["tests_total"] = tests_total
            result["tests_passed"] = tests_passed
            result["tests_failed"] = tests_failed
            result["all_tests_counted"] = True

        except (json.JSONDecodeError, KeyError) as e:
            print(f"    Warning: Failed to parse {ctrf_path.name}: {e}")

    # Check for reward.txt (binary for benchmark)
    reward_txt_path = verifier_dir / "reward.txt"
    if reward_txt_path.exists():
        try:
            reward_text = reward_txt_path.read_text().strip()
            result["reward"] = float(reward_text)
        except (ValueError, IOError):
            pass

    # Check for reward_partial.txt (function-level partial credit from CTRF)
    reward_partial_path = verifier_dir / "reward_partial.txt"
    if reward_partial_path.exists():
        try:
            result["reward_partial"] = float(reward_partial_path.read_text().strip())
        except (ValueError, IOError):
            pass

    # Check for reward_partial_cases.txt (test-case-level partial credit from JUnit XML)
    reward_partial_cases_path = verifier_dir / "reward_partial_cases.txt"
    if reward_partial_cases_path.exists():
        try:
            result["reward_partial_cases"] = float(reward_partial_cases_path.read_text().strip())
        except (ValueError, IOError):
            pass

    # Try to get reward from result.json (may override reward.txt)
    result_path = trial_dir / "result.json"
    if result_path.exists():
        try:
            with open(result_path) as f:
                trial_result = json.load(f)

            verifier_result = trial_result.get("verifier_result", {})
            if verifier_result:
                rewards = verifier_result.get("rewards", {})
                reward_val = rewards.get("reward")
                if reward_val is not None:
                    result["reward"] = reward_val
        except (json.JSONDecodeError, KeyError):
            pass

    # Task is considered finished ONLY if we have a concrete reward value
    if result["reward"] is not None:
        result["finished_normally"] = True

    return result


def detect_skills_used(job_folder: str, agent: str, task_name: Optional[str] = None) -> bool:
    """
    Detect whether the agent actually used skills during execution.

    Detection methods vary by agent:
    - gemini-cli: Check for "activate_skill" in gemini-cli.trajectory.json
    - claude-code: Check claude-code.txt for Skill tool calls
    - codex: Check if skills folder exists with content in agent folder

    Returns True if skills were used, False otherwise.
    """
    job_path = Path(job_folder)
    if not job_path.is_absolute():
        job_path = JOBS_DIR / job_folder
    if not job_path.exists():
        return False

    # Find trial directory (contains __ in name)
    trial_dir = None
    for item in job_path.iterdir():
        if item.is_dir() and "__" in item.name:
            trial_dir = item
            break

    if not trial_dir:
        return False

    agent_dir = trial_dir / "agent"
    if not agent_dir.exists():
        return False

    def trajectory_mentions_generated_skills() -> bool:
        patterns = ["/app/environment/skills", "environment/skills"]
        candidates = [
            agent_dir / "trajectory.json",
            agent_dir / "codex.txt",
            agent_dir / "claude-code.txt",
            agent_dir / "gemini-cli.trajectory.json",
        ]
        # Also scan any trajectory-like json files
        candidates.extend(
            [p for p in agent_dir.iterdir() if p.is_file() and "trajectory" in p.name.lower()]
        )
        for path in candidates:
            if not path.exists():
                continue
            try:
                content = path.read_text(errors="ignore")
            except Exception:
                continue
            if any(pat in content for pat in patterns):
                return True
        return False

    # If skills were generated into the task environment (no-skills-generate runs),
    # consider that as "used" only when trajectory evidence exists.
    if task_name is None:
        task_name = trial_dir.name.split("__", 1)[0] if "__" in trial_dir.name else None
    if task_name and "no_skills_generate" in TASKS_DIR.name:
        env_skills = TASKS_DIR / task_name / "environment" / "skills"
        if env_skills.exists() and any(env_skills.rglob("*")) and trajectory_mentions_generated_skills():
            return True

    # If we synced generated skills into job logs, count that as used only with trajectory evidence.
    synced_skills = agent_dir / "skills_generated"
    if synced_skills.exists() and any(synced_skills.rglob("*")) and trajectory_mentions_generated_skills():
        return True

    if agent == "gemini-cli":
        # Check for activate_skill in trajectory
        trajectory_path = agent_dir / "gemini-cli.trajectory.json"
        if trajectory_path.exists():
            try:
                content = trajectory_path.read_text()
                return "activate_skill" in content
            except:
                pass
        return False

    elif agent == "claude-code":
        # Check claude-code.txt init line for skills field
        # The first line contains {"type":"system","subtype":"init",...,"skills":[...],...}
        # Filter out Claude Code built-in slash commands — only count task-specific skills
        builtin_skills = {"debug", "simplify", "batch", "loop", "claude-api", "compact", "context", "cost",
                          "heapdump", "init", "pr-comments", "release-notes", "review", "security-review", "insights"}
        txt_path = agent_dir / "claude-code.txt"
        if txt_path.exists():
            try:
                with open(txt_path, 'r') as f:
                    first_line = f.readline().strip()
                if first_line:
                    init_data = json.loads(first_line)
                    skills = init_data.get("skills", [])
                    task_skills = [s for s in skills if s not in builtin_skills]
                    return len(task_skills) > 0
            except (json.JSONDecodeError, IOError):
                pass
        return False

    elif agent in ("codex", "codex-skill-only", "codex-subscription"):
        # Check if skills folder exists with content in agent logs
        skills_path = agent_dir / "skills"
        if skills_path.exists() and skills_path.is_dir():
            # Check if there's any content besides .system
            for item in skills_path.iterdir():
                if item.name != ".system" and item.is_dir():
                    return True
            # Check inside .system for installed skills
            system_path = skills_path / ".system"
            if system_path.exists():
                for item in system_path.iterdir():
                    if item.is_dir() and item.name != "skill-installer" and item.name != "skill-creator":
                        return True
        # Check codex.txt (JSONL trajectory) for skill usage
        codex_txt = agent_dir / "codex.txt"
        if codex_txt.exists():
            try:
                content = codex_txt.read_text(errors="ignore")
                if "/skills/" in content or ".skills/" in content:
                    return True
            except Exception:
                pass
        # Fallback: check trajectory.json
        trajectory_path = agent_dir / "trajectory.json"
        if trajectory_path.exists():
            try:
                content = trajectory_path.read_text()
                return "/skills/" in content or "skill" in content.lower()
            except Exception:
                pass
        return False

    elif agent in ("terminus-2", "terminus-2-evolution"):
        # Check trajectory.json for skill loading
        # terminus-2: skills loaded via {"load_skill": "skill-name"} / "Loaded skill:"
        # terminus-2-evolution: agent creates evo-* skills and imports them directly,
        #   so also check for /skills/ paths and evo- skill references
        trajectory_path = agent_dir / "trajectory.json"
        if trajectory_path.exists():
            try:
                content = trajectory_path.read_text()
                if (
                    '"load_skill"' in content
                    or "Loaded skill:" in content
                    or "/skills/evo-" in content
                    or "skill-creator" in content
                ):
                    return True
            except:
                pass
        return False

    else:
        # For other agents, try generic detection
        # Look for any trajectory file and check for skill keywords
        for f in agent_dir.iterdir():
            if f.suffix == ".json" and "trajectory" in f.name.lower():
                try:
                    content = f.read_text()
                    if "activate_skill" in content or '"Skill"' in content:
                        return True
                except:
                    pass
        return False


def sync_generated_skills(job_folder: str, task_name: str) -> bool:
    """
    Copy generated skills from task environment into the job's agent logs.
    Returns True if skills were copied, False otherwise.
    """
    try:
        job_path = Path(job_folder)
        if not job_path.is_absolute():
            job_path = JOBS_DIR / job_folder
        if not job_path.exists():
            return False

        # Find trial directory (contains __ in name)
        trial_dir = None
        for item in job_path.iterdir():
            if item.is_dir() and "__" in item.name:
                trial_dir = item
                break
        if not trial_dir:
            return False

        src = TASKS_DIR / task_name / "environment" / "skills"
        if not src.exists() or not src.is_dir():
            return False

        dest = trial_dir / "agent" / "skills_generated"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return True
    except Exception:
        return False


def archive_existing_skills(task_name: str) -> Optional[Path]:
    """
    Archive evolved skills (evo-*), evolution state, and verifier scripts before a fresh run.

    Only moves evo-* skill directories — pre-installed static skills are
    preserved so the Dockerfile ``COPY skills ...`` commands still work.
    Also archives ``environment/verifier/`` (agent-generated surrogate verifier
    scripts) so the next run starts without prior verifier contamination.
    Returns the archive path if anything was archived, otherwise None.
    """
    guard_bundled_tasks_immutable(TASKS_DIR)
    try:
        task_env = TASKS_DIR / task_name / "environment"
        skills_dir = task_env / "skills"

        # Collect only evolved skill directories (evo-* prefix)
        evo_dirs = []
        if skills_dir.exists() and skills_dir.is_dir():
            evo_dirs = [d for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith("evo-")]

        evo_dir = task_env / ".evolution"
        has_evo_state = evo_dir.exists() and any(evo_dir.iterdir())

        verifier_dir = task_env / "verifier"
        has_verifier = verifier_dir.exists() and any(verifier_dir.iterdir())

        if not evo_dirs and not has_evo_state and not has_verifier:
            return None

        archive_root = task_env.parent / "skills_archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = archive_root / timestamp
        # Ensure uniqueness
        if dest.exists():
            suffix = 1
            while (archive_root / f"{timestamp}-{suffix}").exists():
                suffix += 1
            dest = archive_root / f"{timestamp}-{suffix}"
        dest.mkdir(parents=True, exist_ok=True)

        # Move only evo-* skill directories into the archive
        for evo_skill in evo_dirs:
            shutil.move(str(evo_skill), str(dest / evo_skill.name))
        if evo_dirs:
            print(f"    Archived {len(evo_dirs)} evolved skills: {[d.name for d in evo_dirs]}")

        # Also reset evolution state so next run starts fresh
        if has_evo_state:
            history_file = evo_dir / "history.jsonl"
            library_file = evo_dir / "library.json"
            # Archive evolution state alongside skills
            evo_archive = dest / ".evolution"
            evo_archive.mkdir(parents=True, exist_ok=True)
            if history_file.exists():
                shutil.copy2(str(history_file), str(evo_archive / "history.jsonl"))
                history_file.unlink()
            if library_file.exists():
                shutil.copy2(str(library_file), str(evo_archive / "library.json"))
                library_file.unlink()
            # Clean up oracle_stop.json to prevent stale results leaking into the next run
            oracle_stop_file = evo_dir / "oracle_stop.json"
            if oracle_stop_file.exists():
                shutil.copy2(str(oracle_stop_file), str(evo_archive / "oracle_stop.json"))
                oracle_stop_file.unlink()
            print(f"    Archived evolution state to {dest.name}")

        # Archive verifier scripts (agent-generated surrogate tests)
        if has_verifier:
            verifier_archive = dest / "verifier"
            shutil.move(str(verifier_dir), str(verifier_archive))
            print(f"    Archived verifier scripts to {dest.name}/verifier")

        return dest
    except Exception:
        return None


def _archive_killed_run(task_name: str, model: str, tasks_dir: Path) -> None:
    """Archive evolution artifacts from killed/incomplete runs.

    Checks experiments/<model_subdir>/evolution_results.csv and
    completed_evolution_tasks.csv. If neither has a successful record
    for this task, any on-disk artifacts are orphaned and get archived.
    """
    guard_bundled_tasks_immutable(tasks_dir)
    task_env = tasks_dir / task_name / "environment"
    skills_dir = task_env / "skills"

    # Check if there are any evolution artifacts on disk
    has_evo_skills = skills_dir.exists() and any(d for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith("evo-"))
    has_verifier = (task_env / "verifier").exists() and any((task_env / "verifier").iterdir())
    has_evo_state = (task_env / ".evolution").exists() and any((task_env / ".evolution").iterdir())

    if not has_evo_skills and not has_verifier and not has_evo_state:
        return

    subdir = _model_subdir(model)

    # Check evolution_results.csv
    evo_csv = EXPERIMENTS_DIR / subdir / "evolution_results.csv"
    if evo_csv.exists():
        with open(evo_csv) as f:
            for row in csv.DictReader(f):
                if row.get("task") == task_name:
                    try:
                        if int(row.get("tests_total", 0) or 0) > 0:
                            return  # Has valid evolution result
                    except (ValueError, TypeError):
                        pass

    # Check completed_evolution_tasks.csv
    completed_csv = EXPERIMENTS_DIR / subdir / "completed_evolution_tasks.csv"
    if completed_csv.exists():
        with open(completed_csv) as f:
            for row in csv.DictReader(f):
                if row.get("task") == task_name:
                    if row.get("evo_doc_acc", "").strip():
                        return  # Has recorded accuracy

    # No successful record in either CSV → archive
    archive_path = archive_existing_skills(task_name)
    if archive_path:
        print(f"    Archived killed-run artifacts for {task_name} → {archive_path.name}")


# ============================================================================
# TASK DISCOVERY
# ============================================================================

def get_available_tasks(tasks_dir: Path) -> List[str]:
    """Get list of valid task directories (those with task.toml)."""
    tasks = []
    for task_path in tasks_dir.iterdir():
        if task_path.is_dir() and (task_path / "task.toml").exists():
            tasks.append(task_path.name)
    return sorted(tasks)


# ============================================================================
# JOB NAME GENERATION
# ============================================================================

AGENT_SHORT_NAMES = {
    "terminus-2-evolution": "t2evo",
    "terminus-2": "t2",
    "claude-code-skills": "claudeskill",
    "claude-code-skill-only": "claudeskillonly",
    "codex-skill-only": "codexskillonly",
    "codex-subscription": "codexsubscription",
}


def generate_job_name(
    agent: str,
    model: str,
    task: str,
    difficulty: Optional[str] = None,
    sequential_run: Optional[int] = None,
) -> str:
    """
    Generate a unique job name for the experiment.
    Format: {agent_short}-{model_short}-{task_clean}-{seqN}-{hash}
    """
    agent_short = AGENT_SHORT_NAMES.get(agent, agent)
    model_short = model.split("/")[-1] if "/" in model else model
    model_short = model_short.replace("-preview", "").replace("-", "").replace(":", "")[:15]
    task_clean = task.replace("_", "-")[:30]
    time_hash = hashlib.md5(f"{time.time()}{task}{model}".encode()).hexdigest()[:6]

    parts = [agent_short, model_short, task_clean]
    if sequential_run is not None and sequential_run > 1:
        parts.append(f"seq{sequential_run}")
    parts.append(time_hash)

    job_name = "-".join(parts)
    job_name = re.sub(r"[^a-zA-Z0-9\-_]", "-", job_name)
    return job_name


# ============================================================================
# SKILLS HANDLING
# ============================================================================

# ============================================================================
# HARBOR EXPERIMENT RUNNER
# ============================================================================

def run_harbor_experiment(
    task_path: Union[str, Path],
    model: str,
    agent: str = "claude-code",
    job_name: Optional[str] = None,
    timeout: int = 7200,
    timeout_multiplier: float = 1.0,
    jobs_dir: Optional[Path] = None,
    force_build: bool = False,
    agent_kwargs: Optional[Dict[str, object]] = None,
    disable_verification: bool = False,
) -> dict:
    """
    Run a single harbor experiment.

    Args:
        task_path: Path to the task directory
        model: Model name (e.g., 'google/gemini-3-flash')
        agent: Agent name (default: 'claude-code')
        job_name: Custom job name
        timeout: Timeout in seconds (default: 2 hours)

    Returns:
        Dictionary with experiment results
    """
    task_path = Path(task_path)

    # Build command - don't use -a if we have a custom agent import path
    # (using -a overrides --agent-import-path)
    agent_import_path = AGENT_IMPORT_PATHS.get(agent)
    if agent_import_path:
        cmd = ["uv", "run", "harbor", "run", "-p", str(task_path), "-m", model]
        cmd.extend(["--agent-import-path", agent_import_path])
    else:
        cmd = ["uv", "run", "harbor", "run", "-p", str(task_path), "-a", agent, "-m", model]

    if jobs_dir:
        cmd.extend(["--jobs-dir", str(jobs_dir)])

    if job_name:
        cmd.extend(["--job-name", job_name])

    if timeout_multiplier != 1.0:
        cmd.extend(["--timeout-multiplier", str(timeout_multiplier)])

    if force_build:
        cmd.append("--force-build")

    if disable_verification:
        cmd.append("--disable-verification")

    # Pass agent kwargs (e.g. evolution_phase) via harbor --agent-kwarg
    if agent_kwargs and agent_import_path:
        for key, value in agent_kwargs.items():
            if isinstance(value, bool):
                arg_value = "true" if value else "false"
            else:
                arg_value = str(value)
            cmd.extend(["--agent-kwarg", f"{key}={arg_value}"])

    print(f"Running: {' '.join(cmd)}")

    try:
        # Re-read .env to pick up rotated tokens (e.g. AWS_BEARER_TOKEN_BEDROCK)
        _refresh_env_from_dotenv()
        env = os.environ.copy()
        # Remove __PYVENV_LAUNCHER__ to prevent stale Python path from leaking
        # into uv's subprocess (causes "No module named 'encodings'" when the
        # parent process was launched by a different Python installation).
        env.pop("__PYVENV_LAUNCHER__", None)
        # Ensure child process Python output is unbuffered for real-time streaming
        env["PYTHONUNBUFFERED"] = "1"

        started_at = datetime.now().isoformat()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            # Harbor is launched through an ``uv`` wrapper.  A plain
            # ``process.kill()`` only kills that wrapper and can leave Harbor
            # (plus its trial container) running as an orphan after the outer
            # experiment timeout.  Give every trial its own process group so
            # timeout cleanup can target the complete launch tree.
            start_new_session=True,
        )
        captured_lines: list[str] = []

        # Read stdout in a background thread so we can enforce a timeout
        def _reader():
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    print(line, end="", flush=True)
                    captured_lines.append(line)
            except (OSError, ValueError):
                # Timeout cleanup may close the pipe after terminating the
                # complete process group.  That is expected and must not leak
                # an exception from this daemon reader thread.
                return

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as timeout_error:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise timeout_error
        finally:
            reader_thread.join(timeout=10)
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
            reader_thread.join(timeout=1)
        finished_at = datetime.now().isoformat()
        captured_stdout = "".join(captured_lines)

        job_folder = job_name
        if not job_folder:
            match = re.search(r"Results written to jobs/([^/]+)/", captured_stdout)
            if match:
                job_folder = match.group(1)

        return_val = {
            "success": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": captured_stdout,
            "stderr": "",
            "job_folder": job_folder,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except subprocess.TimeoutExpired:
        return_val = {
            "success": False,
            "returncode": -1,
            "stdout": "".join(captured_lines) if "captured_lines" in locals() else "",
            "stderr": "Timeout expired",
            "job_folder": job_name,
            "started_at": started_at if 'started_at' in locals() else None,
            "finished_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return_val = {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "job_folder": job_name,
            "started_at": None,
            "finished_at": None,
        }
    return return_val


# ============================================================================
# EXPERIMENT RUNNER
# ============================================================================

def run_experiments(
    tasks: List[str],
    model_configs: List[Tuple[str, str]],
    max_parallel: int = 4,
    dry_run: bool = False,
    skip_completed: bool = True,
    timeout: int = 7200,
    timeout_multiplier: float = 1.0,
    jobs_dir: Optional[Path] = None,
    difficulty: Optional[str] = None,
    force_build: bool = False,
    sync_skills: bool = False,
    archive_skills: bool = False,
    sequential_runs: int = 1,
    gt_oracle_model: Optional[str] = None,
    max_iterations: Optional[int] = None,
    max_episodes: Optional[int] = None,
    independent_verifier_model: Optional[str] = None,
    gt_oracle_agent: Optional[str] = None,
    skip_surrogate_verifier: bool = False,
    continue_evolution: bool = False,
) -> List[dict]:
    """
    Run experiments locally with parallel execution and CSV tracking.

    When ``sequential_runs > 1``, each task is run N times sequentially.
    Each run gets a fresh LLM context and Docker container, while the
    SkillLibrary on disk bridges evolved skills across runs.
    """
    # Load existing runs to determine run indices
    existing_runs = load_existing_runs()

    # Calculate run indices for each model+agent combo
    run_indices = {}
    for model, agent in model_configs:
        key = (model, agent)
        run_indices[key] = get_next_run_index(model, agent, existing_runs)

    print("\nRun indices for this experiment:")
    for (model, agent), idx in run_indices.items():
        print(f"  {model} ({agent}): run_index = {idx}")

    # Build set of already completed tasks for skip logic
    # Key: (task, model, agent, condition) — condition distinguishes variants
    current_condition = detect_condition(str(TASKS_DIR), model_configs[0][1] if model_configs else "")
    completed_tasks = set()
    if skip_completed:
        evolution_agents = {agent for _, agent in model_configs if agent == "terminus-2-evolution"}
        # Per-task CSVs are the primary record for every agent. Scan the selected
        # task variant so continuation runs do not repeat completed canary tasks.
        for model, agent in model_configs:
            subdir = _model_subdir(model)
            tasks_dir_name = Path(str(TASKS_DIR)).name if TASKS_DIR else "tasks"
            variant_dir = EXPERIMENTS_DIR / subdir / tasks_dir_name
            if not variant_dir.exists():
                continue
            for task_csv in variant_dir.glob("*/results.csv"):
                task_name = task_csv.parent.name
                with open(task_csv, "r", newline="") as f:
                    for row in csv.DictReader(f):
                        if row.get("model") != model or row.get("agent") != agent:
                            continue
                        try:
                            tests_total = int(row.get("tests_total", 0) or 0)
                        except (ValueError, TypeError):
                            tests_total = 0
                        if tests_total <= 0:
                            continue
                        if agent == "terminus-2-evolution" and row.get("exit_reason") != "gt_oracle_pass":
                            continue
                        row_condition = row.get("condition", "")
                        completed_tasks.add((task_name, model, agent, row_condition))
        # For non-evolution agents, use model-specific baseline_results.csv
        for run in existing_runs:
            if run.get("agent") in evolution_agents:
                continue
            try:
                tests_total = int(run.get("tests_total", 0) or 0)
            except (ValueError, TypeError):
                tests_total = 0
            if tests_total > 0:
                run_condition = run.get("condition", "")
                if not run_condition:
                    raw_dir = run.get("tasks_dir", "")
                    run_condition = detect_condition(raw_dir, run.get("agent", "")) if raw_dir else ""
                completed_tasks.add((run.get("task"), run.get("model"), run.get("agent"), run_condition))

    results_lock = threading.Lock()
    experiment_results: List[dict] = []

    def run_single(
        task_name: str,
        model: str,
        agent: str,
        run_index: int,
        run_id: int,
        total: int,
        sequential_run: int = 1,
    ) -> dict:
        task_path = TASKS_DIR / task_name
        task_difficulty = get_task_difficulty(task_name)
        job_name = generate_job_name(
            agent, model, task_name,
            difficulty=task_difficulty,
            sequential_run=sequential_run if sequential_runs > 1 else None,
        )

        seq_label = f" [seq {sequential_run}/{sequential_runs}]" if sequential_runs > 1 else ""
        print(f"\n[{run_id}/{total}]{seq_label} Starting: {task_name}")
        print(f"    Model: {model}")
        print(f"    Agent: {agent}")
        print(f"    Difficulty: {task_difficulty}")
        print(f"    Run index: {run_index}")
        if sequential_runs > 1:
            print(f"    Sequential run: {sequential_run}/{sequential_runs}")
        print(f"    Job name: {job_name}")

        if dry_run:
            import_path = AGENT_IMPORT_PATHS.get(agent)
            agent_route = (
                f"--agent-import-path {import_path}"
                if import_path
                else f"-a {agent}"
            )
            print(
                f"    [DRY RUN] Would run: harbor run -p {task_path} "
                f"{agent_route} -m {model}"
            )
            return {"task": task_name, "model": model, "agent": agent, "status": "dry_run", "difficulty": task_difficulty}

        # Only archive skills on the first sequential run
        if archive_skills and sequential_run == 1:
            archive_existing_skills(task_name)

        # Build agent-specific kwargs
        extra_agent_kwargs: Dict[str, object] = {}
        if agent == "terminus-2-evolution":
            if sequential_runs > 1:
                extra_agent_kwargs["sequential_run"] = sequential_run
            if gt_oracle_model:
                extra_agent_kwargs["gt_oracle_model"] = gt_oracle_model
            if max_iterations is not None:
                extra_agent_kwargs["max_host_interventions"] = max_iterations
            if max_episodes is not None:
                extra_agent_kwargs["max_episodes"] = max_episodes
            if independent_verifier_model:
                extra_agent_kwargs["independent_verifier_model"] = independent_verifier_model
            if gt_oracle_agent:
                extra_agent_kwargs["gt_oracle_agent"] = gt_oracle_agent
            if timeout_multiplier != 1.0:
                extra_agent_kwargs["timeout_multiplier"] = timeout_multiplier
            if skip_surrogate_verifier:
                extra_agent_kwargs["skip_surrogate_verifier"] = True

        # Only force build on the first sequential run (image doesn't change between runs)
        effective_force_build = force_build and sequential_run == 1

        # Run the experiment
        result = run_harbor_experiment(
            task_path, model, agent,
            job_name=job_name,
            timeout=timeout,
            timeout_multiplier=timeout_multiplier,
            jobs_dir=jobs_dir,
            force_build=effective_force_build,
            agent_kwargs=extra_agent_kwargs or None,
            disable_verification=agent == "terminus-2-evolution",
        )

        # Resolve the actual job folder path for result checking.
        # harbor writes results under --jobs-dir/job_name, but if --jobs-dir
        # is not used, results go to the default jobs/ directory.
        actual_job_path = job_name
        if result.get("job_folder"):
            candidate = JOBS_DIR / result["job_folder"]
            if candidate.exists():
                actual_job_path = str(candidate.resolve())
            else:
                # Try default jobs/ directory as fallback
                fallback = JOBS_DIR / result["job_folder"]
                if fallback.exists():
                    actual_job_path = str(fallback.resolve())
                    print(f"    Found results at fallback path: {fallback}")

        # Check completion status
        completion = check_task_completion(actual_job_path)

        # Override with GT oracle reward when available (the evolution container
        # may have stale outputs, but the oracle ran in a clean container with
        # evolved skills — its score is the meaningful metric regardless of pass/fail).
        oracle_stop_file = task_path / "environment" / ".evolution" / "oracle_stop.json"
        if oracle_stop_file.exists():
            try:
                oracle_data = json.loads(oracle_stop_file.read_text(encoding="utf-8"))
                gt_res = oracle_data.get("gt_result")
                if gt_res:
                    oracle_reward = gt_res.get("reward")
                    oracle_passed = gt_res.get("tests_passed", 0)
                    oracle_total = gt_res.get("total_tests", 0)
                    if oracle_reward is not None:
                        print(
                            f"    Oracle override: reward {completion['reward']} → {oracle_reward}"
                            f" (oracle {oracle_passed}/{oracle_total} GT tests, passed={gt_res.get('passed')})"
                        )
                        completion["reward"] = oracle_reward
                        # Oracle reward is test-case-level, use it for partial credits too
                        completion["reward_partial"] = oracle_reward
                        completion["reward_partial_cases"] = oracle_reward
                        completion["tests_passed"] = oracle_passed
                        completion["tests_total"] = oracle_total
                        completion["tests_failed"] = oracle_total - oracle_passed
                        completion["finished_normally"] = True
                        completion["all_tests_counted"] = True
            except (json.JSONDecodeError, OSError) as e:
                print(f"    Warning: could not read oracle_stop.json: {e}")

        # Some benchmark verifiers expose one binary/continuous task-level
        # reward but report 0/0 unit tests when the submitted program fails to
        # compile. That is a real evaluated failure, not missing verifier
        # evidence. Represent it as one task-level verifier outcome so
        # missing-only retries do not give direct baselines a second stochastic
        # attempt. Evolution remains stricter: its score must come from the
        # fresh GT oracle with concrete GT test counts above.
        if (
            agent != "terminus-2-evolution"
            and completion["finished_normally"]
            and completion["tests_total"] == 0
            and completion["reward"] is not None
        ):
            task_passed = int(float(completion["reward"]) >= 1.0)
            completion["tests_total"] = 1
            completion["tests_passed"] = task_passed
            completion["tests_failed"] = 1 - task_passed
            completion["all_tests_counted"] = True

        # Detect if skills were actually used
        skills_used = detect_skills_used(actual_job_path, agent, task_name)

        # Optionally copy generated skills into job logs
        if sync_skills:
            sync_generated_skills(actual_job_path, task_name)

        # Calculate duration
        duration_sec = None
        if result.get("started_at") and result.get("finished_at"):
            try:
                start = datetime.fromisoformat(result["started_at"])
                end = datetime.fromisoformat(result["finished_at"])
                duration_sec = (end - start).total_seconds()
            except:
                pass

        # Extract GT oracle data from evolution_run_log.json
        gt_oracle_data = _extract_gt_oracle_from_log(actual_job_path)

        # Prepare CSV row
        csv_row = {
            "job_name": job_name,
            "task": task_name,
            "model": model,
            "agent": agent,
            "run_index": run_index,
            "sequential_run": sequential_run,
            "skills_used": skills_used,
            "finished_normally": completion["finished_normally"],
            "all_tests_counted": completion["all_tests_counted"],
            "tests_total": completion["tests_total"],
            "tests_passed": completion["tests_passed"],
            "tests_failed": completion["tests_failed"],
            "reward": completion["reward"],
            "reward_partial": completion.get("reward_partial"),
            "reward_partial_cases": completion.get("reward_partial_cases"),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
            "duration_sec": duration_sec,
            "difficulty": task_difficulty,
            "tasks_dir": str(TASKS_DIR),
            "gt_oracle_passed": gt_oracle_data.get("passed"),
            "gt_oracle_model": gt_oracle_data.get("model"),
            "gt_oracle_duration_sec": gt_oracle_data.get("duration_sec"),
        }

        # Never turn an agent/provider exception into a completed benchmark row.
        # Harbor can return exit code 0 while recording an exception in the trial,
        # so the absence of a concrete verifier/GT reward is the authoritative
        # signal. Valid task failures still have a numeric reward of 0.0.
        harbor_failed = result.get("returncode", -1) != 0
        no_results = not completion["finished_normally"]
        if no_results:
            reason = "process failed" if harbor_failed else "no concrete reward"
            print(f"⏭️  [{run_id}/{total}]{seq_label} Skipping CSV record ({reason}): {task_name}")
            print(f"    Return code: {result.get('returncode')}")
            stderr_text = result.get("stderr", "")
            if stderr_text:
                print(f"    Stderr (last 500): {stderr_text[-500:]}")
            return {
                "task": task_name,
                "model": model,
                "agent": agent,
                "status": "failed",
                "difficulty": task_difficulty,
            }

        # Write to per-task structured experiment logs (thread-safe: different tasks → different dirs)
        with results_lock:
            try:
                record_run_result(csv_row)
            except Exception as e:
                print(f"    Warning: failed to record result: {e}")

        # Copy evolution artifacts into structured experiments/ directory
        if "evolution" in agent:
            try:
                started_at = csv_row.get("started_at") or ""
                run_dir = _resolve_run_dir(model, str(TASKS_DIR), task_name, started_at)
                _copy_run_artifacts(run_dir, job_name, str(TASKS_DIR), task_name)
            except Exception as e:
                print(f"    Warning: failed to copy run artifacts: {e}")

        # Print status
        if completion["finished_normally"]:
            status_emoji = "✅" if completion["all_tests_counted"] else "⚠️"
            skills_emoji = "🛠️" if skills_used else "🚫"
            print(f"{status_emoji} [{run_id}/{total}]{seq_label} Finished: {task_name} ({task_difficulty})")
            print(f"    Tests: {completion['tests_passed']}/{completion['tests_total']} passed")
            print(f"    Reward: {completion['reward']}")
            print(f"    Skills: used={skills_used} {skills_emoji}")

            # Print evolution intervention summary if available
            if agent == "terminus-2-evolution":
                _print_evolution_summary(actual_job_path)
        else:
            print(f"❌ [{run_id}/{total}]{seq_label} Failed: {task_name} ({task_difficulty})")
            print(f"    Return code: {result.get('returncode')}")
            print(f"    Job path resolved: {actual_job_path}")
            stderr_text = result.get("stderr", "")
            if stderr_text:
                print(f"    Stderr (last 500): {stderr_text[-500:]}")
            stdout_text = result.get("stdout", "")
            if stdout_text:
                print(f"    Stdout (last 500): {stdout_text[-500:]}")

        return {
            "task": task_name,
            "model": model,
            "agent": agent,
            "status": "finished" if completion["finished_normally"] else "failed",
            "difficulty": task_difficulty,
            **csv_row,
        }

    # Build list of experiments to run
    experiments_to_run = []
    for model, agent in model_configs:
        run_index = run_indices[(model, agent)]
        for task_name in tasks:
            combo_key = (task_name, model, agent, current_condition)
            if skip_completed and combo_key in completed_tasks:
                print(f"Skipping (already completed): {task_name} with {model}")
                experiment_results.append({
                    "task": task_name,
                    "status": "skipped_completed",
                    "model": model,
                    "agent": agent,
                    "difficulty": get_task_difficulty(task_name),
                })
            else:
                # Preserve on-disk skills when the caller explicitly requests
                # continuation.  The killed-run cleanup is only appropriate for
                # implicit/default runs; applying it to --continue-evolution
                # silently removes the very evo-* skills meant to be continued.
                if (
                    agent == "terminus-2-evolution"
                    and not archive_skills
                    and not continue_evolution
                ):
                    _archive_killed_run(task_name, model, TASKS_DIR)
                experiments_to_run.append((task_name, model, agent, run_index))

    total_runs = len(experiments_to_run)
    total_with_sequential = total_runs * sequential_runs
    print(f"\n{'=' * 70}")
    print("EXPERIMENT SUMMARY")
    print(f"{'=' * 70}")
    print(f"Difficulty filter: {difficulty}")
    print(f"Total experiments to run: {total_runs}")
    if sequential_runs > 1:
        print(f"Sequential runs per task: {sequential_runs}")
        print(f"Total runs (tasks x sequential): {total_with_sequential}")
    print(f"Already completed (skipped): {len(tasks) * len(model_configs) - total_runs}")
    print(f"Max parallel workers: {max_parallel}")
    print(f"Timeout per task: {timeout}s ({timeout/3600:.1f} hours)")
    print(f"Results dir: {EXPERIMENTS_DIR}")
    print(f"{'=' * 70}")

    if total_runs > 0 and not dry_run:
        if sequential_runs > 1:
            # Sequential multi-run evolution: run each round to completion before starting the next.
            # Within each round, tasks run in parallel across model configs.
            for seq_round in range(1, sequential_runs + 1):
                # Check for oracle early-stop signals from previous rounds
                if seq_round > 1 and gt_oracle_model:
                    remaining = []
                    for exp in experiments_to_run:
                        exp_task_name = exp[0]
                        stop_file = TASKS_DIR / exp_task_name / "environment" / ".evolution" / "oracle_stop.json"
                        if stop_file.exists():
                            print(f"    Skipping {exp_task_name} — oracle stop signal found")
                        else:
                            remaining.append(exp)
                    experiments_to_run = remaining
                    if not experiments_to_run:
                        print("All tasks passed oracle check — stopping evolution early")
                        break

                print(f"\n{'=' * 70}")
                print(f"SEQUENTIAL ROUND {seq_round}/{sequential_runs}")
                print(f"{'=' * 70}")

                with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                    future_to_exp = {
                        executor.submit(
                            run_single, task, model, agent, run_index,
                            i + 1, total_runs,
                            sequential_run=seq_round,
                        ): (task, model, agent)
                        for i, (task, model, agent, run_index) in enumerate(experiments_to_run)
                    }

                    for future in as_completed(future_to_exp):
                        task, model, agent = future_to_exp[future]
                        try:
                            result_entry = future.result()
                        except Exception as e:
                            result_entry = {
                                "task": task,
                                "model": model,
                                "agent": agent,
                                "status": "exception",
                                "error": str(e),
                                "difficulty": get_task_difficulty(task),
                            }
                            print(f"💥 Exception for {task}: {e}")

                        experiment_results.append(result_entry)

                print(f"\nRound {seq_round}/{sequential_runs} complete.")
        else:
            # Standard single-round execution
            with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                future_to_exp = {
                    executor.submit(run_single, task, model, agent, run_index, i + 1, total_runs): (task, model, agent)
                    for i, (task, model, agent, run_index) in enumerate(experiments_to_run)
                }

                for future in as_completed(future_to_exp):
                    task, model, agent = future_to_exp[future]
                    try:
                        result_entry = future.result()
                    except Exception as e:
                        result_entry = {
                            "task": task,
                            "model": model,
                            "agent": agent,
                            "status": "exception",
                            "error": str(e),
                            "difficulty": get_task_difficulty(task),
                        }
                        print(f"💥 Exception for {task}: {e}")

                    experiment_results.append(result_entry)

    elif dry_run:
        for seq_round in range(1, sequential_runs + 1):
            if sequential_runs > 1:
                print(f"\n--- DRY RUN: Sequential round {seq_round}/{sequential_runs} ---")
            for i, (task, model, agent, run_index) in enumerate(experiments_to_run, 1):
                result = run_single(task, model, agent, run_index, i, total_runs, sequential_run=seq_round)
                experiment_results.append(result)

    return experiment_results


def print_final_summary(results: List[dict], model_configs: List[Tuple[str, str]], difficulty: str):
    """Print final experiment summary."""
    print(f"\n{'=' * 70}")
    print("FINAL SUMMARY")
    print(f"{'=' * 70}")
    print(f"Difficulty filter: {difficulty}")

    # Count by status
    status_counts = {}
    for r in results:
        status = r.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nBy status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    # Count by difficulty
    difficulty_counts = {}
    for r in results:
        diff = r.get("difficulty", "unknown")
        difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1

    print("\nBy difficulty:")
    for diff, count in sorted(difficulty_counts.items()):
        print(f"  {diff}: {count}")

    # Show finished tasks with test results
    finished = [r for r in results if r.get("status") == "finished"]
    if finished:
        print(f"\nFinished tasks ({len(finished)}):")
        for r in finished:
            passed = r.get("tests_passed", 0)
            total = r.get("tests_total", 0)
            reward = r.get("reward", "N/A")
            all_counted = "✓" if r.get("all_tests_counted") else "✗"
            diff = r.get("difficulty", "unknown")
            print(f"  {r['task']} ({diff}): {passed}/{total} tests [{all_counted}], reward={reward}")

    # Show failed tasks
    failed = [r for r in results if r.get("status") == "failed"]
    if failed:
        print(f"\nFailed tasks ({len(failed)}):")
        for r in failed:
            diff = r.get("difficulty", "unknown")
            print(f"  - {r['task']} ({diff})")

    print(f"\nResults saved to: {EXPERIMENTS_DIR}/<model>/evolution_results.csv")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Run SkillsBench experiments locally with CSV tracking and difficulty filtering")
    parser.add_argument(
        "--difficulty", "-d", type=str, default="all",
        choices=["easy", "medium", "hard", "all"],
        help="Task difficulty level to run (default: all)"
    )
    parser.add_argument(
        "--tasks", type=str, default=None,
        help="Tasks to run: 'all', number (e.g., '3' for first 3), or comma-separated list. If not specified, uses difficulty filter."
    )
    parser.add_argument(
        "--exclude-tasks", type=str, default=None,
        help="Comma-separated list of tasks to exclude (e.g., 'mhc-layer-impl,slow-task')"
    )
    parser.add_argument(
        "--only-tasks", type=str, default=None,
        help="Only run these specific tasks (comma-separated). Useful for running slow tasks separately."
    )
    parser.add_argument(
        "--max-parallel", type=int, default=4,
        help="Maximum parallel workers"
    )
    parser.add_argument(
        "--timeout", type=int, default=7200,
        help="Timeout per task in seconds (default: 7200 = 2 hours)"
    )
    parser.add_argument(
        "--timeout-multiplier", type=float, default=1.0,
        help="Multiplier for task timeouts passed to harbor (default: 1.0)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be run without executing"
    )
    parser.add_argument(
        "--no-skip-completed", action="store_true",
        help="Don't skip already completed task+model combinations"
    )
    parser.add_argument(
        "--new-run", action="store_true",
        help="Start a new run (incremented run_index) for all tasks, even if previously completed"
    )
    parser.add_argument(
        "--single-trial-only", action="store_true",
        help=(
            "Atomically bind this output root to one runner invocation; refuse "
            "any same-root restart"
        ),
    )
    parser.add_argument(
        "--force-build", action="store_true",
        help="Force rebuild the environment image for each task"
    )
    parser.add_argument(
        "--sync-skills", action="store_true",
        help="Copy generated skills into job logs (agent/skills_generated)"
    )
    parser.add_argument(
        "--archive-skills", action="store_true",
        help="Move existing generated skills into a timestamped archive before running"
    )

    # Evolution mode: fresh vs continue (mutually exclusive)
    evo_mode_group = parser.add_mutually_exclusive_group()
    evo_mode_group.add_argument(
        "--fresh-evolution", action="store_true", default=False,
        help="Start evolution from scratch: archive existing skills and reset evolution state "
             "(history.jsonl + library.json) before the first run. Default for sequential runs."
    )
    evo_mode_group.add_argument(
        "--continue-evolution", action="store_true", default=False,
        help="Continue evolution from previous state: preserve existing skills and history. "
             "Use this to resume a previously interrupted experiment."
    )
    parser.add_argument(
        "--jobs-dir", type=str, default=None,
        help="Custom jobs directory path. If not specified, auto-generates: {timestamp}-{model}-{agent}-{skills}-{difficulty}-{experimenter}"
    )
    parser.add_argument(
        "--experimenter", "-e", type=str, default=None,
        help="Experimenter name to include in jobs directory name"
    )
    parser.add_argument(
        "--model", "-m", type=str, default=None,
        help="Model name (e.g., 'gemini/gemini-3-pro-preview'). Overrides MODEL_CONFIGS."
    )
    parser.add_argument(
        "--agent", "-a", type=str, default=None,
        help="Agent name (e.g., 'terminus-2', 'gemini-cli', 'claude-code'). Overrides MODEL_CONFIGS."
    )
    parser.add_argument(
        "--agent-import-path",
        action="append",
        default=[],
        metavar="NAME=MODULE:CLASS",
        help=(
            "Register a custom Harbor Agent without editing this repository. "
            "Repeat for multiple adapters."
        ),
    )
    parser.add_argument(
        "--tasks-dir", type=str, default=None,
        help="Custom tasks directory path. Defaults to REPO_ROOT/tasks."
    )
    parser.add_argument(
        "--sequential-runs", type=int, default=1,
        help="Number of sequential runs per task for evolution. Each run gets a fresh context. "
             "Skills evolved in run K carry over to run K+1 via disk. (default: 1)"
    )
    parser.add_argument(
        "--gt-oracle-model", type=str, default=None,
        help="Model for GT oracle check (e.g. openai/gpt-5-mini). "
             "When set, enables early stopping: after surrogate tests pass, a clean agent "
             "re-executes the task with evolved skills and runs ground truth tests. "
             "If GT tests pass, remaining sequential runs for that task are skipped."
    )
    parser.add_argument(
        "--max-iterations", type=int, default=None,
        help="Max evolution iterations (host interventions) per round for terminus-2-evolution. "
             "Overrides the agent's default of 5."
    )
    parser.add_argument(
        "--max-episodes", type=int, default=None,
        help="Absolute cap on evolution-agent command episodes for terminus-2-evolution. "
             "This is separate from --max-iterations/GT feedback cycles."
    )
    parser.add_argument(
        "--independent-verifier-model", type=str, default=None,
        help="Model for the independent verifier agent (default: same as agent model). "
             "The independent verifier uses a separate LLM session to generate and run "
             "pytest scripts, eliminating confirmation bias from the evolution agent."
    )
    parser.add_argument(
        "--skip-surrogate-verifier", action="store_true", default=False,
        help="Skip the independent surrogate verifier and go directly to GT oracle. "
             "Used for ablation experiments to test verifier contribution."
    )
    parser.add_argument(
        "--gt-oracle-agent", type=str, default=None,
        help="Agent type for GT oracle check (default for evolution: "
             "claude-code-skill-only). This release-standard condition physically "
             "removes the background document before a fresh Agent re-executes "
             "the task with the current Skill. Built-in or registered with "
             "--agent-import-path."
    )

    args = parser.parse_args()

    try:
        custom_agent_imports = parse_agent_import_specs(args.agent_import_path)
    except ValueError as exc:
        parser.error(str(exc))
    AGENT_IMPORT_PATHS.update(custom_agent_imports)
    if custom_agent_imports:
        os.environ[CUSTOM_AGENT_IMPORTS_ENV] = json.dumps(
            custom_agent_imports, sort_keys=True
        )
    if (
        args.gt_oracle_agent
        and args.gt_oracle_agent not in GT_ORACLE_AGENT_CHOICES
        and args.gt_oracle_agent not in custom_agent_imports
    ):
        parser.error(
            f"unknown ground-truth Agent {args.gt_oracle_agent!r}; use a built-in "
            "name or register it with --agent-import-path"
        )

    # Determine model configs (CLI overrides file config)
    if args.model and args.agent:
        model_configs = [(args.model, args.agent)]
    elif args.model or args.agent:
        print("Error: Both --model and --agent must be specified together")
        return
    else:
        model_configs = MODEL_CONFIGS

    if not model_configs:
        print("Error: No model configurations specified. Use --model and --agent flags.")
        return

    # Determine jobs directory
    global JOBS_DIR
    if args.jobs_dir:
        jobs_dir = Path(args.jobs_dir)
    else:
        # Auto-generate jobs dir name with timestamp
        model, agent = model_configs[0]
        dir_name = generate_jobs_dir_name(
            model, agent,
            experimenter=args.experimenter,
            difficulty=args.difficulty if args.difficulty != "all" else None
        )
        jobs_dir = TRAJECTORIES_DIR / dir_name

    # Update global JOBS_DIR for completion checking
    JOBS_DIR = jobs_dir

    # Update TASKS_DIR if custom path provided
    global TASKS_DIR
    if args.tasks_dir:
        TASKS_DIR = Path(args.tasks_dir)
        if not TASKS_DIR.exists():
            print(f"Error: Tasks directory does not exist: {TASKS_DIR}")
            return

    enforce_single_trial = args.single_trial_only
    if enforce_single_trial and not args.dry_run:
        try:
            marker = claim_single_trial_run(OUTPUT_ROOT, TASKS_DIR)
            print(f"Single-trial guard claimed: {marker}")
        except FileExistsError:
            print(
                "Error: this run output root was already claimed; "
                "choose a new RUN_ID instead of mixing independent runs"
            )
            raise SystemExit(2)

    jobs_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 70}")
    print("SkillsBench Experiment Runner with Difficulty Support")
    print(f"{'=' * 70}")
    print(f"Repository root: {REPO_ROOT}")
    print(f"Jobs directory: {JOBS_DIR}")
    print(f"Tasks directory: {TASKS_DIR}")
    print(f"Task metadata source: {TASKS_DIR}/<task>/task.toml")
    print(f"Difficulty filter: {args.difficulty}")

    # Determine evolution mode for terminus-2-evolution agent
    # Default: fresh-evolution for sequential runs, no-op for single runs
    fresh_evolution = args.fresh_evolution
    if not args.fresh_evolution and not args.continue_evolution:
        # Neither flag specified: default to fresh for sequential evolution runs
        if args.sequential_runs > 1 and args.agent == "terminus-2-evolution":
            fresh_evolution = True

    # --archive-skills is a legacy alias for --fresh-evolution
    effective_archive = args.archive_skills or fresh_evolution

    task_mutation_requested = effective_archive or any(
        agent == "terminus-2-evolution" for _, agent in model_configs
    )
    workspace_lock = None
    if task_mutation_requested and not args.dry_run:
        try:
            guard_bundled_tasks_immutable(TASKS_DIR)
            workspace_lock = acquire_mutable_tasks_lock(TASKS_DIR)
            print(f"Workspace lock acquired: {workspace_lock.name}")
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    # Fresh evolution must force Docker rebuild so the cached image
    # doesn't retain archived evo-* skills from a previous build.
    if fresh_evolution and not args.force_build:
        args.force_build = True

    if args.agent == "terminus-2-evolution":
        evo_mode = "fresh" if fresh_evolution else "continue"
        print(f"Evolution mode: {evo_mode} ({'archive + reset' if fresh_evolution else 'preserve existing state'})")

    # Get available tasks
    available_tasks = get_available_tasks(TASKS_DIR)
    print(f"\nFound {len(available_tasks)} available tasks")

    # Determine which tasks to run
    if args.only_tasks:
        # Only run specific tasks (useful for slow tasks)
        tasks_to_run = [t.strip() for t in args.only_tasks.split(",")]
        invalid_tasks = [t for t in tasks_to_run if t not in available_tasks]
        if invalid_tasks:
            print(f"Warning: Unknown tasks: {invalid_tasks}")
            tasks_to_run = [t for t in tasks_to_run if t in available_tasks]
    elif args.tasks:
        # Use traditional task specification
        if args.tasks.lower() == "all":
            tasks_to_run = available_tasks
        elif args.tasks.isdigit():
            n = int(args.tasks)
            tasks_to_run = available_tasks[:n]
        else:
            tasks_to_run = [t.strip() for t in args.tasks.split(",")]
            # Validate tasks exist
            invalid_tasks = [t for t in tasks_to_run if t not in available_tasks]
            if invalid_tasks:
                print(f"Warning: Unknown tasks: {invalid_tasks}")
                tasks_to_run = [t for t in tasks_to_run if t in available_tasks]
    else:
        # Use difficulty filter
        tasks_to_run = filter_tasks_by_difficulty(available_tasks, args.difficulty)

    # Apply exclusions
    if args.exclude_tasks:
        exclude_set = set(t.strip() for t in args.exclude_tasks.split(","))
        excluded = [t for t in tasks_to_run if t in exclude_set]
        tasks_to_run = [t for t in tasks_to_run if t not in exclude_set]
        if excluded:
            print(f"Excluded {len(excluded)} tasks: {excluded}")

    print(f"Tasks to run: {len(tasks_to_run)}")

    # Show difficulty distribution
    if tasks_to_run:
        difficulty_dist = {}
        for task in tasks_to_run:
            diff = get_task_difficulty(task)
            difficulty_dist[diff] = difficulty_dist.get(diff, 0) + 1
        print(f"Difficulty distribution: {difficulty_dist}")

    print("\nModel configurations:")
    for i, (model, agent) in enumerate(model_configs, 1):
        print(f"  {i}. {model} (agent: {agent})")

    # Run experiments
    # --new-run implies --no-skip-completed
    skip_completed = not (args.no_skip_completed or args.new_run)

    results = run_experiments(
        tasks=tasks_to_run,
        model_configs=model_configs,
        max_parallel=args.max_parallel,
        dry_run=args.dry_run,
        skip_completed=skip_completed,
        timeout=args.timeout,
        timeout_multiplier=args.timeout_multiplier,
        jobs_dir=jobs_dir,
        difficulty=args.difficulty,
        force_build=args.force_build,
        sync_skills=args.sync_skills,
        archive_skills=effective_archive,
        sequential_runs=args.sequential_runs,
        gt_oracle_model=args.gt_oracle_model,
        max_iterations=args.max_iterations,
        max_episodes=args.max_episodes,
        independent_verifier_model=args.independent_verifier_model,
        gt_oracle_agent=args.gt_oracle_agent,
        skip_surrogate_verifier=args.skip_surrogate_verifier,
        continue_evolution=args.continue_evolution,
    )

    print_final_summary(results, model_configs, args.difficulty)


if __name__ == "__main__":
    main()
