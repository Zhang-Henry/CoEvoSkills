"""ClaudeCode wrapper that forwards Azure Anthropic env vars to the container.

Claude Code CLI inside the container needs ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL
to authenticate via Azure AI Foundry's Anthropic endpoint. It also needs ANTHROPIC_MODEL
set to the Azure deployment name (without provider prefix).

Register in AGENT_IMPORT_PATHS as:
    "azure-claude-code": "libs.terminus_agent.agents.azure_claude_code:AzureClaudeCode"
"""

from __future__ import annotations

import os

from harbor.agents.installed.claude_code import ClaudeCode

_AZURE_ANTHROPIC_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
)


class AzureClaudeCode(ClaudeCode):
    """ClaudeCode subclass that transparently adds Azure Anthropic credentials."""

    def create_run_agent_commands(self, instruction: str):
        exec_inputs = super().create_run_agent_commands(instruction)
        azure_env = {k: os.environ[k] for k in _AZURE_ANTHROPIC_ENV_VARS if os.environ.get(k)}

        # Override ANTHROPIC_MODEL to use Azure deployment name (strip provider prefix)
        # e.g. "anthropic/claude-opus-4-6" -> "claude-opus-4-6"
        if self.model_name:
            model_name = self.model_name.split("/")[-1] if "/" in self.model_name else self.model_name
            azure_env["ANTHROPIC_MODEL"] = model_name

        if azure_env:
            for ei in exec_inputs:
                if ei.env is not None:
                    ei.env.update(azure_env)
                else:
                    ei.env = dict(azure_env)
        return exec_inputs
