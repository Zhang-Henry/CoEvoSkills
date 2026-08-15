"""Claude Code agent for background document-plus-evolved-Skill evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.base import ExecInput
from harbor.models.agent.context import AgentContext
from harbor.environments.base import BaseEnvironment

from libs.terminus_agent.agents.claude_code_vertex import (
    cleanup_vertex_adc,
    configure_vertex_commands,
    ensure_subscription_token,
    ensure_claude_on_path,
    stage_vertex_adc,
    validate_vertex_transcript,
    )


class ClaudeCodeSkills(ClaudeCode):
    """Expose the paired background document and persisted Skills to fresh Claude Code."""

    def __init__(self, *args, **kwargs):
        prompt_path = (
            Path(__file__).resolve().parent
            / "prompt-templates"
            / "claude-skill-transfer.txt"
        )
        kwargs.setdefault("prompt_template_path", prompt_path)
        super().__init__(*args, **kwargs)

    async def setup(self, environment: BaseEnvironment) -> None:
        """Install Claude Code, enforce the paired treatment, and stage skills."""
        ensure_subscription_token()
        await super().setup(environment)
        await ensure_claude_on_path(environment)
        await stage_vertex_adc(environment)

        barrier = await environment.exec(
            command=(
                "test -d /app/environment/doc "
                "&& find /app/environment/doc -type f -name '*.md' -print -quit | grep -q . "
                "&& find /app/environment/skills -mindepth 2 -maxdepth 2 "
                "-name SKILL.md -print -quit | grep -q ."
            ),
            timeout_sec=15,
        )
        if barrier.return_code != 0:
            raise RuntimeError(
                "Claude paired-treatment barrier failed: expected the background document "
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
            raise RuntimeError("Failed to stage evolved skills for Claude Code")

        immutable = await environment.exec(
            command=(
                "find /app/environment/skills/evo-* -type f -exec chmod a-w {} + "
                "2>/dev/null; "
                "find /app/environment/skills/evo-* -type d -exec chmod a-w {} + "
                "2>/dev/null"
            ),
            timeout_sec=15,
        )
        if immutable.return_code != 0:
            raise RuntimeError("Failed to make evolved Skill sources read-only")

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        try:
            await super().run(instruction, environment, context)
        finally:
            await cleanup_vertex_adc(environment)

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        """Run Claude, then make only its JSONL trajectory readable by Harbor."""
        commands = super().create_run_agent_commands(instruction)
        commands.append(
            ExecInput(
                command=(
                    "find /logs/agent/sessions/projects -type f -name '*.jsonl' "
                    "-exec chmod a+r {} +"
                ),
                env=commands[-1].env,
                timeout_sec=15,
            )
        )
        return configure_vertex_commands(commands)

    def _get_session_dir(self) -> Path | None:
        """Select the primary Claude session when Claude spawned subagents.

        Harbor's upstream selector treats every directory containing a JSONL
        file as a primary-session candidate.  Claude Code stores background
        Agent/Task transcripts under nested ``subagents`` directories, so one
        otherwise valid run can appear to have multiple session directories.
        Prefer the session id reported by the native stream transcript, then
        fall back to the single non-subagent JSONL parent.
        """
        project_root = self.logs_dir / "sessions" / "projects"
        if not project_root.exists():
            return None

        candidate_files = list(project_root.glob("**/*.jsonl"))
        if not candidate_files:
            return None

        transcript_session_id: str | None = None
        transcript_path = self.logs_dir / "claude-code.txt"
        if transcript_path.is_file():
            for line in transcript_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = event.get("session_id")
                if isinstance(session_id, str) and session_id:
                    transcript_session_id = session_id

        if transcript_session_id:
            matching_files = [
                path
                for path in candidate_files
                if path.stem == transcript_session_id
                and "subagents" not in path.relative_to(project_root).parts
            ]
            matching_dirs = sorted({path.parent for path in matching_files})
            if len(matching_dirs) == 1:
                return matching_dirs[0]

        primary_files = [
            path
            for path in candidate_files
            if "subagents" not in path.relative_to(project_root).parts
        ]
        primary_dirs = sorted({path.parent for path in primary_files})
        if len(primary_dirs) == 1:
            return primary_dirs[0]

        return super()._get_session_dir()

    def populate_context_post_run(self, context: AgentContext) -> None:
        # Harbor's installed Claude agent prints a diagnostic after serializing
        # the trajectory. A worker can outlive the supervisor pipe that
        # originally owned stdout; in that case the
        # diagnostic raises BrokenPipeError even though Claude completed and
        # the trajectory is already valid.  Treat this as a logging failure,
        # not as an oracle/infrastructure failure.
        try:
            super().populate_context_post_run(context)
        except BrokenPipeError:
            pass
        validate_vertex_transcript(
            self.logs_dir / "claude-code.txt", self.model_name
        )
