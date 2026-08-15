"""Codex agent for strict evolved-Skill-only transfer."""

from __future__ import annotations

import re

from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class CodexSkillOnly(Codex):
    """Expose a frozen evolved Skill, but no background document, to Codex."""

    @staticmethod
    def _skill_transfer_instruction(instruction: str) -> str:
        return (
            "Task-specific Agent Skills are installed under /logs/agent/skills. "
            "Before solving the task, inspect the relevant SKILL.md and follow its "
            "workflow and bundled resources. Treat the installed Skill as read-only. "
            "Complete the task in the working directory and verify the deliverables.\n\n"
            f"{instruction}"
        )

    def create_run_agent_commands(self, instruction: str):
        return super().create_run_agent_commands(
            self._skill_transfer_instruction(instruction)
        )

    async def _setup_skill_only(self, environment: BaseEnvironment) -> None:
        barrier = await environment.exec(
            command=(
                "test ! -e /app/environment/doc "
                "&& find /app/environment/skills -mindepth 2 -maxdepth 2 "
                "-name SKILL.md -print -quit | grep -q ."
            ),
            timeout_sec=15,
        )
        if barrier.return_code != 0:
            raise RuntimeError(
                "Codex Skill-only barrier failed: expected no document path "
                "and at least one evolved Skill"
            )

        staged = await environment.exec(
            command=(
                "mkdir -p /logs/agent/skills && "
                "for skill in /app/environment/skills/*; do "
                "test -f \"$skill/SKILL.md\" || continue; "
                "ln -sfn \"$skill\" \"/logs/agent/skills/$(basename \"$skill\")\"; "
                "done"
            ),
            timeout_sec=15,
        )
        if staged.return_code != 0:
            raise RuntimeError("Failed to stage the evolved Skill for Codex")

        immutable = await environment.exec(
            command=(
                "find /app/environment/skills -type f -exec chmod a-w {} + "
                "2>/dev/null; "
                "find /app/environment/skills -type d -exec chmod a-w {} + "
                "2>/dev/null"
            ),
            timeout_sec=15,
        )
        if immutable.return_code != 0:
            raise RuntimeError("Failed to make evolved Skill sources read-only")

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)
        await self._setup_skill_only(environment)

    async def _skill_digest(self, environment: BaseEnvironment) -> str:
        result = await environment.exec(
            command=(
                "find /app/environment/skills -type f "
                "! -path '*/__pycache__/*' ! -name '*.pyc' -print0 "
                "| sort -z | xargs -0 sha256sum | sha256sum"
            ),
            timeout_sec=15,
        )
        stdout = result.stdout or ""
        matches = re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", stdout)
        if result.return_code != 0 or len(matches) != 1:
            raise RuntimeError(
                "Failed to attest the evolved Skill source tree: "
                f"return_code={result.return_code}, "
                f"stdout={stdout[-300:]!r}, stderr={(result.stderr or '')[-300:]!r}"
            )
        return matches[0]

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        digest_before = await self._skill_digest(environment)
        run_error: BaseException | None = None
        try:
            await super().run(instruction, environment, context)
        except BaseException as exc:
            run_error = exc

        try:
            digest_after = await self._skill_digest(environment)
        except BaseException as digest_error:
            if run_error is not None:
                raise RuntimeError(
                    "Skill post-run attestation failed after the agent failed"
                ) from run_error
            raise digest_error

        if digest_after != digest_before:
            raise RuntimeError(
                "Frozen evolved Skill changed during transfer evaluation"
            ) from run_error
        if run_error is not None:
            raise run_error.with_traceback(run_error.__traceback__)
