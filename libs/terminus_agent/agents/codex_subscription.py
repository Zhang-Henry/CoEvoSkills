"""Codex oracle backed by an existing ChatGPT subscription login.

The stock Harbor Codex agent always creates ``$CODEX_HOME/auth.json`` from
``OPENAI_API_KEY``. CoEvoSkills instead uploads the host Codex CLI login into
an ephemeral, unmounted directory inside the trial container. The credential
never enters the persistent output tree and is removed when the command exits.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from pathlib import Path

from harbor.agents.installed.base import ExecInput
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths

from libs.terminus_agent.agents.codex_skill_only import CodexSkillOnly


class CodexSubscription(CodexSkillOnly):
    """Run strict Skill-only Codex with a staged ChatGPT subscription login."""

    _CONTAINER_CODEX_HOME = "/tmp/coevoskills-codex-home"

    @staticmethod
    def _subscription_auth_source() -> Path:
        configured_auth = os.environ.get("CODEX_CHATGPT_AUTH_FILE")
        auth_source = (
            Path(configured_auth).expanduser()
            if configured_auth
            else Path.home() / ".codex" / "auth.json"
        )
        if not auth_source.is_file():
            raise FileNotFoundError(
                "Codex subscription auth cache not found. Run `codex login` "
                "or set CODEX_CHATGPT_AUTH_FILE."
            )
        return auth_source

    def __init__(
        self,
        reasoning_effort: str | None = None,
        *args,
        **kwargs,
    ):
        if reasoning_effort is None:
            reasoning_effort = os.environ.get("CODEX_REASONING_EFFORT", "low")
        super().__init__(reasoning_effort=reasoning_effort, *args, **kwargs)

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        if not self.model_name:
            raise ValueError("Model name is required")

        codex_home = self._CONTAINER_CODEX_HOME
        output_path = (EnvironmentPaths.agent_dir / self._OUTPUT_FILENAME).as_posix()
        model = shlex.quote(self.model_name.split("/")[-1])
        escaped_instruction = shlex.quote(
            self._skill_transfer_instruction(instruction)
        )
        reasoning_flag = (
            f"-c model_reasoning_effort={shlex.quote(self._reasoning_effort)} "
            if self._reasoning_effort
            else ""
        )

        command = f"""
set -o pipefail
trap 'rm -f "$CODEX_HOME/auth.json"' EXIT HUP INT TERM
if [[ ! -s "$CODEX_HOME/auth.json" ]]; then
    echo "Missing staged ChatGPT subscription login at $CODEX_HOME/auth.json" >&2
    exit 1
fi

codex exec \
    --dangerously-bypass-approvals-and-sandbox \
    --skip-git-repo-check \
    --model {model} \
    --json \
    --enable unified_exec \
    {reasoning_flag}\
    -- {escaped_instruction} \
    2>&1 </dev/null | tee {shlex.quote(output_path)}
codex_status=${{PIPESTATUS[0]}}
exit "$codex_status"
"""

        return [
            ExecInput(
                command=command,
                env={"CODEX_HOME": codex_home},
            )
        ]

    async def setup(self, environment: BaseEnvironment) -> None:
        """Stage the host Codex binary and an empty ephemeral Codex home."""
        self._subscription_auth_source()

        configured_cli = os.environ.get("CODEX_CLI_BINARY")
        cli_source = (
            Path(configured_cli).expanduser()
            if configured_cli
            else Path(shutil.which("codex") or "")
        )
        if not cli_source.is_file():
            raise FileNotFoundError(
                "Host Codex CLI not found. Install `codex` or set "
                "CODEX_CLI_BINARY."
            )
        cli_source = cli_source.resolve()

        try:
            prepared = await environment.exec(
                command=(
                    "mkdir -p /installed-agent "
                    f"{self._CONTAINER_CODEX_HOME} && "
                    f"chmod 0700 {self._CONTAINER_CODEX_HOME}"
                )
            )
            if prepared.return_code != 0:
                raise RuntimeError("Failed to prepare the ephemeral Codex home")
            await environment.upload_file(
                source_path=cli_source,
                target_path="/installed-agent/codex",
            )
            result = await environment.exec(
                command=(
                    "chmod 0755 /installed-agent/codex && "
                    "ln -sf /installed-agent/codex /usr/local/bin/codex && "
                    "codex --version"
                )
            )
            setup_dir = self.logs_dir / "setup"
            setup_dir.mkdir(parents=True, exist_ok=True)
            (setup_dir / "return-code.txt").write_text(str(result.return_code))
            if result.stdout:
                (setup_dir / "stdout.txt").write_text(result.stdout)
            if result.stderr:
                (setup_dir / "stderr.txt").write_text(result.stderr)
            if result.return_code != 0:
                raise RuntimeError(
                    "Failed to stage the offline Codex CLI in the oracle container"
                )
            await self._setup_skill_only(environment)
            linked = await environment.exec(
                command=(
                    f"ln -sfn /logs/agent/skills {self._CONTAINER_CODEX_HOME}/skills"
                )
            )
            if linked.return_code != 0:
                raise RuntimeError("Failed to expose Skills to the Codex subscription")
        except BaseException:
            try:
                await asyncio.shield(
                    environment.exec(
                        command=f"rm -rf {self._CONTAINER_CODEX_HOME}"
                    )
                )
            except BaseException:
                pass
            raise

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        """Upload OAuth just in time and remove its entire ephemeral home."""
        auth_source = self._subscription_auth_source()
        try:
            prepared = await environment.exec(
                command=(
                    f"mkdir -p {self._CONTAINER_CODEX_HOME} && "
                    f"chmod 0700 {self._CONTAINER_CODEX_HOME}"
                )
            )
            if prepared.return_code != 0:
                raise RuntimeError("Failed to prepare the ephemeral Codex home")
            await environment.upload_file(
                source_path=auth_source,
                target_path=f"{self._CONTAINER_CODEX_HOME}/auth.json",
            )
            protected = await environment.exec(
                command=f"chmod 0600 {self._CONTAINER_CODEX_HOME}/auth.json"
            )
            if protected.return_code != 0:
                raise RuntimeError("Failed to protect the staged Codex credential")
            await super().run(instruction, environment, context)
        finally:
            try:
                await asyncio.shield(
                    environment.exec(
                        command=f"rm -rf {self._CONTAINER_CODEX_HOME}"
                    )
                )
            except BaseException:
                pass
