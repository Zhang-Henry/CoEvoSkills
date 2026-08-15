"""ClaudeCode wrapper that forwards AWS Bedrock env vars to the container.

Harbor's built-in ClaudeCode agent only forwards ANTHROPIC_API_KEY / OAUTH_TOKEN.
This wrapper adds CLAUDE_CODE_USE_BEDROCK and AWS_* variables so that the Claude
CLI inside the container can authenticate via AWS Bedrock.

Register in AGENT_IMPORT_PATHS as:
    "claude-code": "libs.terminus_agent.agents.bedrock_claude_code:BedrockClaudeCode"
"""

from __future__ import annotations

import os

from harbor.agents.installed.claude_code import ClaudeCode

_BEDROCK_ENV_VARS = (
    "CLAUDE_CODE_USE_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_REGION_NAME",
    "AWS_PROFILE",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION",
)


class BedrockClaudeCode(ClaudeCode):
    """ClaudeCode subclass that transparently adds Bedrock credentials."""

    def create_run_agent_commands(self, instruction: str):
        exec_inputs = super().create_run_agent_commands(instruction)
        bedrock_env = {k: os.environ[k] for k in _BEDROCK_ENV_VARS if os.environ.get(k)}
        if bedrock_env:
            for ei in exec_inputs:
                if ei.env is not None:
                    ei.env.update(bedrock_env)
                else:
                    ei.env = dict(bedrock_env)
        return exec_inputs
