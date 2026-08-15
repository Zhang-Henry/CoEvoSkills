from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from harbor.agents.installed.base import ExecInput
from libs.terminus_agent.agents import claude_code_skill_only as module
from libs.terminus_agent.agents.claude_code_skill_only import ClaudeCodeSkillOnly
from libs.terminus_agent.agents.claude_code_vertex import configure_vertex_commands
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

    async def exec(self, **kwargs):
        self.commands.append(kwargs["command"])
        return next(self.results)


def test_skill_only_prompt_exposes_only_skill() -> None:
    prompt = (
        Path(module.__file__).resolve().parent
        / "prompt-templates/claude-skill-only-transfer.txt"
    ).read_text(encoding="utf-8")
    assert "/app/environment/skills/*/SKILL.md" in prompt
    assert "/app/environment/doc" not in prompt
    assert "background document" not in prompt


def test_skill_only_setup_enforces_absent_doc_and_present_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module, "ensure_subscription_token", lambda: None)
    monkeypatch.setattr(module.ClaudeCode, "setup", _noop_async)
    monkeypatch.setattr(module, "ensure_claude_on_path", _noop_async)
    monkeypatch.setattr(module, "stage_vertex_adc", _noop_async)
    environment = _Environment([_Result(), _Result(), _Result()])
    agent = ClaudeCodeSkillOnly(
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )

    asyncio.run(agent.setup(environment))

    assert "test ! -e /app/environment/doc" in environment.commands[0]
    assert "SKILL.md" in environment.commands[0]
    assert "ln -sfn" in environment.commands[1]
    assert "chmod a-w" in environment.commands[2]


def test_skill_only_setup_fails_closed_when_barrier_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module, "ensure_subscription_token", lambda: None)
    monkeypatch.setattr(module.ClaudeCode, "setup", _noop_async)
    monkeypatch.setattr(module, "ensure_claude_on_path", _noop_async)
    monkeypatch.setattr(module, "stage_vertex_adc", _noop_async)
    environment = _Environment([_Result(return_code=1)])
    agent = ClaudeCodeSkillOnly(
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )

    with pytest.raises(RuntimeError, match="Skill-only barrier failed"):
        asyncio.run(agent.setup(environment))


def test_skill_only_run_accepts_unchanged_frozen_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.ClaudeCodeSkills, "run", _noop_run)
    digest = "a" * 64
    environment = _Environment(
        [_Result(stdout=f"{digest}\n"), _Result(stdout=f"{digest}\n")]
    )
    agent = ClaudeCodeSkillOnly(
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )

    asyncio.run(agent.run("instruction", environment, object()))

    assert len(environment.commands) == 2
    assert all("sha256sum" in command for command in environment.commands)


def test_skill_only_run_rejects_mutated_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _noop_run(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.ClaudeCodeSkills, "run", _noop_run)
    environment = _Environment(
        [
            _Result(stdout=f"{'a' * 64}\n"),
            _Result(stdout=f"{'b' * 64}\n"),
        ]
    )
    agent = ClaudeCodeSkillOnly(
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )

    with pytest.raises(RuntimeError, match="Skill changed"):
        asyncio.run(agent.run("instruction", environment, object()))


def test_evolution_oracle_factory_supports_skill_only(tmp_path: Path) -> None:
    agent = HarborTerminus2Evolution._create_oracle_agent(
        object(),
        "claude-code-skill-only",
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )

    assert isinstance(agent, ClaudeCodeSkillOnly)


def test_evolution_skill_only_oracle_physically_removes_background_doc() -> None:
    import inspect

    source = inspect.getsource(HarborTerminus2Evolution._run_gt_oracle_check)
    assert 'self._gt_oracle_agent == "claude-code-skills"' in source
    assert "Every release-standard oracle is Skill-only" in source
    assert "rm -rf -- /app/environment/doc" in source
    assert "test ! -e /app/environment/doc" in source
    assert "GT oracle Skill-only barrier failed" in source


def test_bedrock_skill_only_commands_receive_only_bedrock_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_SUBSCRIPTION",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-token")

    commands = [
        ExecInput(
            command="claude -p task",
            env={
                "ANTHROPIC_API_KEY": "must-be-removed",
                "ANTHROPIC_MODEL": "us.anthropic.claude-opus-4-6-v1",
            },
        )
    ]
    configured = configure_vertex_commands(commands)
    env = configured[0].env or {}

    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert env["AWS_REGION"] == "us-east-2"
    assert env["AWS_BEARER_TOKEN_BEDROCK"] == "test-token"
    assert env["ANTHROPIC_MODEL"] == "us.anthropic.claude-opus-4-6-v1"
    assert "ANTHROPIC_API_KEY" not in env


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("Skill", {"skill": "evo-example"}),
        (
            "Read",
            {"file_path": "/root/.claude/skills/evo-example/SKILL.md"},
        ),
        (
            "Bash",
            {
                "command": (
                    "python /app/environment/skills/evo-example/scripts/run.py"
                )
            },
        ),
    ],
)
def test_evolution_oracle_detects_native_and_manual_skill_use(
    tmp_path: Path,
    tool_name: str,
    tool_input: dict[str, str],
) -> None:
    trace = tmp_path / "claude-code.txt"
    trace.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": tool_name,
                            "input": tool_input,
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert HarborTerminus2Evolution._claude_trace_used_evolved_skill(
        trace,
        {"evo-example"},
    )


def test_evolution_oracle_rejects_unrelated_file_read_as_skill_use(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    trace.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/root/input.json"},
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert not HarborTerminus2Evolution._claude_trace_used_evolved_skill(
        trace,
        {"evo-example"},
    )
