"""Provider authentication and provenance checks for containerized Claude Code.

Claude Code can run through Vertex AI, Amazon Bedrock, the Anthropic API, or a
host Claude subscription. Explicit cloud/subscription routes are mutually
exclusive. The module stages only the selected credentials and fails closed
unless the transcript proves the requested provider and exact model were used.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from harbor.agents.installed.base import ExecInput
from harbor.environments.base import BaseEnvironment


CONTAINER_ADC_PATH = "/installed-agent/.vertex/adc.json"
DEFAULT_SUBSCRIPTION_MODEL = "claude-opus-4-6"


class ClaudeCodeProviderError(RuntimeError):
    """Claude Code did not complete a valid call through the selected provider."""


def vertex_enabled() -> bool:
    """Return whether this Claude Code invocation should use Vertex AI."""
    return os.environ.get("CLAUDE_CODE_USE_VERTEX", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def subscription_enabled() -> bool:
    """Return whether this invocation must use the Claude Code subscription."""
    return os.environ.get("CLAUDE_CODE_USE_SUBSCRIPTION", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def bedrock_enabled() -> bool:
    """Return whether this Claude Code invocation should use Bedrock."""
    return os.environ.get("CLAUDE_CODE_USE_BEDROCK", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _validate_provider_selection() -> None:
    enabled = [vertex_enabled(), subscription_enabled(), bedrock_enabled()]
    if sum(enabled) > 1:
        raise RuntimeError(
            "Claude Code provider is ambiguous: enable only one of Vertex, "
            "Bedrock, or subscription"
        )


def _subscription_credentials_path() -> Path:
    configured = os.environ.get("CLAUDE_CREDENTIALS_FILE")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".claude" / ".credentials.json"
    )


def _read_subscription_oauth(path: Path) -> tuple[str, int]:
    if not path.is_file():
        raise RuntimeError(f"Claude Code credentials are unavailable: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Claude Code credentials are invalid: {path}") from exc

    oauth = payload.get("claudeAiOauth") if isinstance(payload, dict) else None
    if not isinstance(oauth, dict):
        raise RuntimeError("Claude Code subscription credentials contain no OAuth record")
    token = oauth.get("accessToken")
    expires_at = oauth.get("expiresAt")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Claude Code subscription access token is unavailable")
    try:
        expires_at_ms = int(expires_at or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Claude Code subscription expiry is invalid") from exc
    return token, expires_at_ms


def ensure_subscription_token() -> None:
    """Load, and when needed refresh, the host subscription OAuth credential.

    Each evolution worker is a separate host process and may run for hours
    before reaching GT.  Reading the token only in the launcher therefore
    permits it to expire mid-campaign.  A cross-process lock serializes the
    refresh probe, and the credential value is never written to logs.
    """
    _validate_provider_selection()
    if not subscription_enabled():
        return

    credentials_path = _subscription_credentials_path()
    lock_path = Path(
        os.environ.get(
            "CLAUDE_SUBSCRIPTION_AUTH_LOCK",
            str(credentials_path.parent / ".coevoskills-auth.lock"),
        )
    ).expanduser()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        with os.fdopen(lock_fd, "r+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            token, expires_at_ms = _read_subscription_oauth(credentials_path)
            refresh_margin_seconds = int(
                os.environ.get("CLAUDE_SUBSCRIPTION_REFRESH_MARGIN_SECONDS", "3600")
            )
            now_ms = int(time.time() * 1000)
            if expires_at_ms <= now_ms + refresh_margin_seconds * 1000:
                claude_binary = shutil.which("claude")
                if not claude_binary:
                    raise RuntimeError(
                        "Claude Code CLI is unavailable for subscription refresh"
                    )
                refresh_env = os.environ.copy()
                for key in (
                    "CLAUDE_CODE_USE_VERTEX",
                    "CLAUDE_CODE_USE_SUBSCRIPTION",
                    "CLAUDE_CODE_OAUTH_TOKEN",
                    "ANTHROPIC_API_KEY",
                    "ANTHROPIC_AUTH_TOKEN",
                    "ANTHROPIC_BASE_URL",
                ):
                    refresh_env.pop(key, None)
                completed = subprocess.run(
                    [
                        claude_binary,
                        "-p",
                        "--model",
                        "claude-haiku-4-5",
                        "--output-format",
                        "json",
                        "--no-session-persistence",
                        "Reply with exactly AUTH_OK",
                    ],
                    env=refresh_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=180,
                )
                if completed.returncode != 0:
                    raise RuntimeError(
                        "Claude Code could not refresh the Max subscription credential"
                    )
                token, expires_at_ms = _read_subscription_oauth(credentials_path)
                now_ms = int(time.time() * 1000)

            if expires_at_ms <= now_ms:
                raise RuntimeError("Claude Code subscription credential is expired")
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token
    except Exception:
        # os.fdopen owns and closes lock_fd once entered.  Before that point,
        # close it here without ever exposing credential material.
        try:
            os.close(lock_fd)
        except OSError:
            pass
        raise


def _host_adc_path() -> Path:
    configured = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if configured:
        path = Path(configured).expanduser()
    else:
        config_home = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )
        path = config_home / "gcloud" / "application_default_credentials.json"

    if not path.is_file():
        raise RuntimeError(f"Google ADC file is unavailable: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Google ADC file is invalid: {path}") from exc
    if not isinstance(payload, dict) or not payload.get("type"):
        raise RuntimeError(f"Google ADC file has no credential type: {path}")
    return path


async def stage_vertex_adc(environment: BaseEnvironment) -> None:
    """Copy ADC into the ephemeral trial container without logging its value."""
    if not vertex_enabled():
        return

    if not os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID"):
        raise RuntimeError(
            "ANTHROPIC_VERTEX_PROJECT_ID is required for Vertex Claude Code"
        )
    if not os.environ.get("CLOUD_ML_REGION"):
        raise RuntimeError("CLOUD_ML_REGION is required for Vertex Claude Code")

    host_adc = _host_adc_path()
    prepared = await environment.exec(
        command=(
            "rm -rf -- /installed-agent/.vertex "
            "&& install -d -m 700 /installed-agent/.vertex"
        ),
        timeout_sec=15,
    )
    if prepared.return_code != 0:
        raise RuntimeError("Failed to prepare the container ADC directory")

    await environment.upload_file(host_adc, CONTAINER_ADC_PATH)
    protected = await environment.exec(
        command=f"chmod 400 {CONTAINER_ADC_PATH}",
        timeout_sec=15,
    )
    if protected.return_code != 0:
        raise RuntimeError("Failed to protect the container ADC file")


async def ensure_claude_on_path(environment: BaseEnvironment) -> None:
    """Expose a working Claude binary to later non-interactive shells.

    Some benchmark images carry a stale ``/usr/local/bin/claude`` wrapper, and
    Harbor's installer can place a fresh CLI under NVM while leaving that
    wrapper first on PATH.  Merely checking ``command -v`` therefore accepts a
    binary that cannot actually start.  Validate candidates by executing
    ``--version`` and, as a final image-agnostic fallback, install into a
    temporary prefix before atomically replacing the stale fixed prefix.
    """
    result = await environment.exec(
        command=(
            "set -eu; "
            "works() { test -x \"$1\" && \"$1\" --version >/dev/null 2>&1; }; "
            "current=$(command -v claude 2>/dev/null || true); "
            "if test -n \"$current\" && works \"$current\"; then exit 0; fi; "
            "claude_bin=$(find /root/.nvm /etc/skel/.nvm "
            "\\( -type f -o -type l \\) -path '*/bin/claude' "
            "-print 2>/dev/null | while IFS= read -r candidate; do "
            "if works \"$candidate\"; then printf '%s\\n' \"$candidate\"; break; fi; "
            "done); "
            "if test -n \"$claude_bin\"; then "
            "ln -sfn \"$claude_bin\" /usr/local/bin/claude; "
            "works /usr/local/bin/claude && exit 0; "
            "fi; "
            "if command -v npm >/dev/null 2>&1; then "
            "repair=/opt/claude-code.repair.$$; rm -rf -- \"$repair\"; "
            "npm install --silent --no-audit --no-fund -g --prefix \"$repair\" "
            "@anthropic-ai/claude-code@latest; "
            "test -e \"$repair/bin/claude\"; "
            "rm -rf -- /opt/claude-code; mv \"$repair\" /opt/claude-code; "
            "ln -sfn /opt/claude-code/bin/claude /usr/local/bin/claude; "
            "fi; "
            "works /usr/local/bin/claude"
        ),
        timeout_sec=180,
    )
    if result.return_code != 0:
        raise RuntimeError("Claude Code was installed but is not executable")


def configure_vertex_commands(commands: list[ExecInput]) -> list[ExecInput]:
    """Pin commands to the explicitly selected provider and exact model.

    The function handles each explicitly selected provider route.
    """
    _validate_provider_selection()
    if not vertex_enabled() and not subscription_enabled() and not bedrock_enabled():
        return commands

    if subscription_enabled():
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if not token:
            raise RuntimeError("Claude Code subscription token was not staged")
        expected_model = os.environ.get(
            "CLAUDE_CODE_SUBSCRIPTION_MODEL", DEFAULT_SUBSCRIPTION_MODEL
        )
        for command in commands:
            env = dict(command.env or {})
            for key in (
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_AUTH_TOKEN",
                "ANTHROPIC_BASE_URL",
                "CLAUDE_CODE_USE_VERTEX",
                "GOOGLE_APPLICATION_CREDENTIALS",
            ):
                env.pop(key, None)
            env.update(
                {
                    "CLAUDE_CODE_OAUTH_TOKEN": token,
                    "ANTHROPIC_MODEL": expected_model,
                    "ANTHROPIC_DEFAULT_OPUS_MODEL": expected_model,
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": expected_model,
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": expected_model,
                    "CLAUDE_CODE_SUBAGENT_MODEL": expected_model,
                }
            )
            command.env = env
        return commands

    if bedrock_enabled():
        region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region:
            raise RuntimeError("AWS_REGION is required for Bedrock Claude Code")
        credential_names = (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_BEARER_TOKEN_BEDROCK",
        )
        if not any(os.environ.get(name) for name in credential_names):
            raise RuntimeError(
                "Bedrock credentials are unavailable; export a bearer token or "
                "short-lived AWS access credentials"
            )
        requested_model = os.environ.get("ANTHROPIC_MODEL")
        if not requested_model:
            for command in commands:
                command_model = (command.env or {}).get("ANTHROPIC_MODEL")
                if command_model:
                    requested_model = command_model
                    break
        for command in commands:
            env = dict(command.env or {})
            for key in (
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_AUTH_TOKEN",
                "ANTHROPIC_BASE_URL",
                "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_USE_VERTEX",
                "GOOGLE_APPLICATION_CREDENTIALS",
            ):
                env.pop(key, None)
            env.update(
                {
                    "CLAUDE_CODE_USE_BEDROCK": "1",
                    "AWS_REGION": region,
                    "AWS_DEFAULT_REGION": region,
                }
            )
            for key in credential_names + (
                "ANTHROPIC_SMALL_FAST_MODEL",
                "ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION",
            ):
                if os.environ.get(key):
                    env[key] = os.environ[key]
            if requested_model:
                env["ANTHROPIC_MODEL"] = requested_model.removeprefix("bedrock/")
            command.env = env
        return commands

    project_id = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
    region = os.environ.get("CLOUD_ML_REGION")
    if not project_id or not region:
        raise RuntimeError(
            "Vertex Claude Code requires ANTHROPIC_VERTEX_PROJECT_ID and "
            "CLOUD_ML_REGION"
        )

    for command in commands:
        env = dict(command.env or {})
        for key in (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_BASE_URL",
            "CLAUDE_CODE_OAUTH_TOKEN",
        ):
            env.pop(key, None)

        env.update(
            {
                "CLAUDE_CODE_USE_VERTEX": "1",
                "CLOUD_ML_REGION": region,
                "ANTHROPIC_VERTEX_PROJECT_ID": project_id,
                "GOOGLE_APPLICATION_CREDENTIALS": CONTAINER_ADC_PATH,
            }
        )

        # Keep foreground and delegated work on the same pinned model so the
        # benchmark condition is unambiguous.
        model = env.get("ANTHROPIC_MODEL")
        if model:
            env.update(
                {
                    "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
                    "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
                    "CLAUDE_CODE_SUBAGENT_MODEL": model,
                }
            )
        command.env = env

    return commands


async def cleanup_vertex_adc(environment: BaseEnvironment) -> None:
    """Best-effort credential cleanup, including agent error/timeout paths."""
    if not vertex_enabled():
        return
    try:
        await environment.exec(
            command=f"rm -f -- {CONTAINER_ADC_PATH}",
            timeout_sec=15,
        )
    except Exception:
        # Trial teardown deletes the container. Cleanup must not mask the
        # original agent/provider exception.
        return


def validate_vertex_transcript(
    log_path: Path, expected_model: str | None = None
) -> None:
    """Reject API failures and prove the selected provider and exact model.

    The historical name is kept for compatibility with existing agents.
    """
    _validate_provider_selection()
    if not vertex_enabled() and not subscription_enabled() and not bedrock_enabled():
        return
    if not log_path.is_file():
        raise ClaudeCodeProviderError("Claude Code produced no provider transcript")

    final_result: dict | None = None
    for raw_line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            final_result = event

    if final_result is None:
        raise ClaudeCodeProviderError("Claude Code produced no final result event")
    if final_result.get("is_error") or final_result.get("api_error_status"):
        status = final_result.get("api_error_status")
        reason = final_result.get("terminal_reason") or final_result.get("result")
        raise ClaudeCodeProviderError(
            f"Claude Code provider request failed (status={status}, reason={reason})"
        )

    model_usage = final_result.get("modelUsage") or {}
    usage_records = [
        usage for usage in model_usage.values() if isinstance(usage, dict)
    ] if isinstance(model_usage, dict) else []
    providers = {
        usage.get("provider")
        for usage in usage_records
        if isinstance(usage.get("provider"), str)
    }
    if vertex_enabled():
        required_provider = "vertex"
    elif bedrock_enabled():
        required_provider = "bedrock"
    else:
        required_provider = "firstParty"
    if providers != {required_provider}:
        raise ClaudeCodeProviderError(
            "Claude Code provider mismatch: "
            f"expected {required_provider}, observed {sorted(providers)}"
        )

    required_model = expected_model
    if subscription_enabled():
        required_model = required_model or os.environ.get(
            "CLAUDE_CODE_SUBSCRIPTION_MODEL", DEFAULT_SUBSCRIPTION_MODEL
        )
    if required_model:
        required_model = required_model.split("/")[-1]
        observed_models = {
            usage.get("canonicalModel") or model_key
            for model_key, usage in model_usage.items()
            if isinstance(model_key, str) and isinstance(usage, dict)
        } if isinstance(model_usage, dict) else set()
        if observed_models != {required_model}:
            raise ClaudeCodeProviderError(
                "Claude Code model mismatch: "
                f"expected {required_model}, observed {sorted(observed_models)}"
            )
