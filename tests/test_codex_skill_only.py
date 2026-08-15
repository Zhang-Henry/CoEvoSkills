from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import run_exp
from libs.terminus_agent.agents import codex_skill_only as module
from libs.terminus_agent.agents.codex_skill_only import CodexSkillOnly
from libs.terminus_agent.agents.codex_subscription import CodexSubscription
from libs.terminus_agent.agents.terminus_2.harbor_terminus_2_evolution import (
    HarborTerminus2Evolution,
)


class _Result:
    def __init__(self, return_code: int = 0, stdout: str = ""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = ""


class _Environment:
    def __init__(self, results: list[_Result]):
        self.results = iter(results)
        self.commands: list[str] = []
        self.uploads: list[tuple[Path, str]] = []

    async def exec(self, **kwargs):
        self.commands.append(kwargs["command"])
        return next(self.results)

    async def upload_file(self, *, source_path: Path, target_path: str):
        self.uploads.append((source_path, target_path))


def test_codex_prompt_points_to_installed_skill(tmp_path: Path) -> None:
    agent = CodexSkillOnly(logs_dir=tmp_path, model_name="openai/gpt-5.4")
    commands = agent.create_run_agent_commands("Complete the task.")
    rendered = "\n".join(command.command for command in commands)

    assert "/logs/agent/skills" in rendered
    assert "SKILL.md" in rendered
    assert "/app/environment/doc" not in rendered


def test_codex_subscription_is_reported_as_skill_only() -> None:
    assert run_exp.detect_condition("/prepared/tasks", "codex-subscription") == (
        "skill_only"
    )


def test_codex_skill_only_is_a_supported_gt_oracle(tmp_path: Path) -> None:
    assert "codex-skill-only" in run_exp.GT_ORACLE_AGENT_CHOICES

    evolution = object.__new__(HarborTerminus2Evolution)
    oracle = evolution._create_oracle_agent(
        "codex-skill-only", tmp_path, "openai/gpt-5.4"
    )

    assert isinstance(oracle, CodexSkillOnly)


def test_evolution_does_not_stage_subscription_auth_in_persistent_logs() -> None:
    assert not hasattr(HarborTerminus2Evolution, "_stage_codex_subscription_auth")


def test_codex_skill_only_setup_enforces_barrier_and_stages_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.Codex, "setup", _noop_async)
    environment = _Environment([_Result(), _Result(), _Result()])
    agent = CodexSkillOnly(logs_dir=tmp_path, model_name="openai/gpt-5.4")

    asyncio.run(agent.setup(environment))

    assert "test ! -e /app/environment/doc" in environment.commands[0]
    assert "SKILL.md" in environment.commands[0]
    assert "/logs/agent/skills" in environment.commands[1]
    assert "ln -sfn" in environment.commands[1]
    assert "chmod a-w" in environment.commands[2]


def test_codex_skill_only_setup_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.Codex, "setup", _noop_async)
    environment = _Environment([_Result(return_code=1)])
    agent = CodexSkillOnly(logs_dir=tmp_path, model_name="openai/gpt-5.4")

    with pytest.raises(RuntimeError, match="Skill-only barrier failed"):
        asyncio.run(agent.setup(environment))


def test_codex_subscription_uses_chatgpt_login_and_skill_prompt(
    tmp_path: Path,
) -> None:
    agent = CodexSubscription(logs_dir=tmp_path, model_name="openai/gpt-5.4")
    commands = agent.create_run_agent_commands("Complete the task.")
    rendered = commands[0].command

    assert "Missing staged ChatGPT subscription login" in rendered
    assert "--model gpt-5.4" in rendered
    assert "/logs/agent/skills" in rendered
    assert "SKILL.md" in rendered
    assert "trap 'rm -f" in rendered
    assert commands[0].env == {"CODEX_HOME": "/tmp/coevoskills-codex-home"}
    assert not (tmp_path / "auth.json").exists()


def test_codex_subscription_stages_auth_only_during_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(CodexSkillOnly, "run", _noop_run)
    auth_source = tmp_path / "source-auth.json"
    auth_source.write_text("temporary credential", encoding="utf-8")
    cli_source = tmp_path / "codex"
    cli_source.write_text("binary placeholder", encoding="utf-8")
    monkeypatch.setenv("CODEX_CHATGPT_AUTH_FILE", str(auth_source))
    monkeypatch.setenv("CODEX_CLI_BINARY", str(cli_source))
    logs_dir = tmp_path / "persistent-logs"
    environment = _Environment([_Result() for _ in range(3)])
    agent = CodexSubscription(logs_dir=logs_dir, model_name="openai/gpt-5.4")

    asyncio.run(agent.run("instruction", environment, object()))

    assert (auth_source, "/tmp/coevoskills-codex-home/auth.json") in environment.uploads
    assert not (logs_dir / "auth.json").exists()
    assert environment.commands[-1] == "rm -rf /tmp/coevoskills-codex-home"


def test_codex_subscription_setup_exposes_skill_without_uploading_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_source = tmp_path / "source-auth.json"
    auth_source.write_text("temporary credential", encoding="utf-8")
    cli_source = tmp_path / "codex"
    cli_source.write_text("binary placeholder", encoding="utf-8")
    monkeypatch.setenv("CODEX_CHATGPT_AUTH_FILE", str(auth_source))
    monkeypatch.setenv("CODEX_CLI_BINARY", str(cli_source))
    environment = _Environment([_Result() for _ in range(6)])
    agent = CodexSubscription(
        logs_dir=tmp_path / "persistent-logs", model_name="openai/gpt-5.4"
    )

    asyncio.run(agent.setup(environment))

    assert all(source != auth_source for source, _target in environment.uploads)
    assert any(
        "ln -sfn /logs/agent/skills /tmp/coevoskills-codex-home/skills"
        in command
        for command in environment.commands
    )


def test_codex_subscription_removes_container_auth_when_run_is_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _cancel_run(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(CodexSkillOnly, "run", _cancel_run)
    auth_source = tmp_path / "source-auth.json"
    auth_source.write_text("temporary credential", encoding="utf-8")
    monkeypatch.setenv("CODEX_CHATGPT_AUTH_FILE", str(auth_source))
    environment = _Environment([_Result() for _ in range(3)])
    agent = CodexSubscription(
        logs_dir=tmp_path / "persistent-logs", model_name="openai/gpt-5.4"
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(agent.run("instruction", environment, object()))

    assert environment.commands[-1] == "rm -rf /tmp/coevoskills-codex-home"


def test_codex_subscription_fails_closed_when_auth_permissions_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_source = tmp_path / "source-auth.json"
    auth_source.write_text("temporary credential", encoding="utf-8")
    monkeypatch.setenv("CODEX_CHATGPT_AUTH_FILE", str(auth_source))
    environment = _Environment([_Result(), _Result(return_code=1), _Result()])
    agent = CodexSubscription(
        logs_dir=tmp_path / "persistent-logs", model_name="openai/gpt-5.4"
    )

    with pytest.raises(RuntimeError, match="Failed to protect"):
        asyncio.run(agent.run("instruction", environment, object()))

    assert environment.commands[-1] == "rm -rf /tmp/coevoskills-codex-home"


def test_codex_subscription_cleans_container_auth_after_setup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth_source = tmp_path / "source-auth.json"
    auth_source.write_text("temporary credential", encoding="utf-8")
    cli_source = tmp_path / "codex"
    cli_source.write_text("binary placeholder", encoding="utf-8")
    monkeypatch.setenv("CODEX_CHATGPT_AUTH_FILE", str(auth_source))
    monkeypatch.setenv("CODEX_CLI_BINARY", str(cli_source))
    environment = _Environment([_Result(), _Result(return_code=1), _Result()])
    agent = CodexSubscription(
        logs_dir=tmp_path / "persistent-logs", model_name="openai/gpt-5.4"
    )

    with pytest.raises(RuntimeError, match="Failed to stage"):
        asyncio.run(agent.setup(environment))

    assert environment.commands[-1] == "rm -rf /tmp/coevoskills-codex-home"


def test_codex_skill_only_run_rejects_mutated_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.Codex, "run", _noop_run)
    environment = _Environment(
        [_Result(stdout=f"{'a' * 64}\n"), _Result(stdout=f"{'b' * 64}\n")]
    )
    agent = CodexSkillOnly(logs_dir=tmp_path, model_name="openai/gpt-5.4")

    with pytest.raises(RuntimeError, match="Skill changed"):
        asyncio.run(agent.run("instruction", environment, object()))


@pytest.mark.parametrize("agent_name", ["codex-skill-only", "codex-subscription"])
def test_result_collector_detects_codex_skill_use(
    tmp_path: Path, agent_name: str
) -> None:
    job = tmp_path / "job"
    agent_dir = job / "example-task__trial" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "codex.txt").write_text(
        '{"type":"item.completed","item":{"command":'
        '"sed -n 1,80p /logs/agent/skills/evo-example/SKILL.md"}}\n',
        encoding="utf-8",
    )

    assert run_exp.detect_skills_used(str(job), agent_name, "example-task")
