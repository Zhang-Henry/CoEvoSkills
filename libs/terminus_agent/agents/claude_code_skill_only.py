"""Claude Code agent for strict evolved-Skill-only transfer."""

from __future__ import annotations

import re
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from libs.terminus_agent.agents.claude_code_skills import ClaudeCodeSkills
from libs.terminus_agent.agents.claude_code_vertex import (
    ensure_subscription_token,
    ensure_claude_on_path,
    stage_vertex_adc,
)


class ClaudeCodeSkillOnly(ClaudeCodeSkills):
    """Expose a frozen evolved Skill, but no background document, to Claude."""

    def __init__(self, *args, **kwargs):
        prompt_path = (
            Path(__file__).resolve().parent
            / "prompt-templates"
            / "claude-skill-only-transfer.txt"
        )
        kwargs.setdefault("prompt_template_path", prompt_path)
        super().__init__(*args, **kwargs)

    async def setup(self, environment: BaseEnvironment) -> None:
        """Install Claude and fail closed unless the Skill-only barrier holds."""
        ensure_subscription_token()
        # Bypass ClaudeCodeSkills.setup because that class intentionally
        # requires the paired background document-plus-Skill condition.
        await ClaudeCode.setup(self, environment)
        await ensure_claude_on_path(environment)
        await stage_vertex_adc(environment)

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
                "Claude Skill-only barrier failed: expected no document path "
                "and at least one evolved Skill"
            )

        staged = await environment.exec(
            command=(
                "mkdir -p /root/.claude/skills && "
                "for skill in /app/environment/skills/*; do "
                "test -f \"$skill/SKILL.md\" || continue; "
                "ln -sfn \"$skill\" \"/root/.claude/skills/$(basename \"$skill\")\"; "
                "done"
            ),
            timeout_sec=15,
        )
        if staged.return_code != 0:
            raise RuntimeError("Failed to stage the evolved Skill for Claude Code")

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

    async def _skill_digest(self, environment: BaseEnvironment) -> str:
        """Return a stable digest of the frozen Skill source tree."""
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
        """Run once and reject the trial if the frozen Skill changed."""
        digest_before = await self._skill_digest(environment)
        run_error: BaseException | None = None
        try:
            await super().run(instruction, environment, context)
        except BaseException as exc:  # Preserve cancellation and agent failures.
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
