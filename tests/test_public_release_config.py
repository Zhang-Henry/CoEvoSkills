from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_wrapper_defaults_are_provider_consistent() -> None:
    wrapper = (REPO_ROOT / "scripts" / "run_condition.sh").read_text(
        encoding="utf-8"
    )

    assert 'DEFAULT_MODEL="anthropic/claude-opus-4-6"' in wrapper
    assert '${GT_ORACLE_MODEL:-$MODEL}' in wrapper
    assert '${VERIFIER_MODEL:-$MODEL}' in wrapper
    assert '${GT_ORACLE_MODEL:-vertex_ai/' not in wrapper
    assert '${VERIFIER_MODEL:-vertex_ai/' not in wrapper


def test_public_wrapper_uses_run_scoped_workspaces_and_single_trial_guard() -> None:
    wrapper = (REPO_ROOT / "scripts" / "run_condition.sh").read_text(
        encoding="utf-8"
    )

    assert '$WORKSPACE_ROOT/$RUN_ID/$CONDITION' in wrapper
    assert "--single-trial-only" in wrapper
    assert 'EVOLUTION_MODE="${EVOLUTION_MODE:-fresh}"' in wrapper
    assert "--continue-evolution" in wrapper
    assert '$ROOT/prepared/$CONDITION' not in wrapper


def test_internal_agent_readme_points_to_public_meta_skill() -> None:
    readme = (REPO_ROOT / "libs" / "terminus_agent" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "meta_skills/skill-creator/" in readme
    assert "compatibility fallback" in readme
