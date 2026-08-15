# Model provider setup

CoEvoSkills separates the model from the Agent harness. `MODEL` and
`VERIFIER_MODEL` select the LiteLLM route used by the evolution generator and
surrogate verifier. Native CLI Agents select authentication separately: Claude
Code uses exactly one of `CLAUDE_CODE_USE_SUBSCRIPTION`,
`CLAUDE_CODE_USE_VERTEX`, or `CLAUDE_CODE_USE_BEDROCK`; Codex subscription uses
`codex login`. A provider-qualified model name alone does not select a native
CLI route.

Copy `.env.example` to `.env`, enable only one Agent-provider block, and never
commit the resulting file. Task-specific credentials are separate: a benchmark
task may require an additional API even when the Agent uses another provider.

## Paper settings

| Variable | Purpose | Paper setting |
|---|---|---|
| `MODEL` | Skill Generator model | Claude Opus 4.6 or GPT-5.2 |
| `AGENT` | Evolution harness | `terminus-2-evolution` |
| `VERIFIER_MODEL` | Independent surrogate verifier | Same backbone as `MODEL` |
| `GT_ORACLE_MODEL` | Fresh Skill-only test model | Same backbone as `MODEL` |
| `GT_ORACLE_AGENT` | Fresh Skill-only executor | `claude-code-skill-only`, `codex-skill-only`, or `codex-subscription` |
| `MAX_GT_ITERATIONS` | Maximum ground-truth interventions | `5` |
| `MAX_PARALLEL` | Concurrent tasks | Start at `1`; paper runs used up to `4` for evolution |

Common model strings are:

| Provider | Example |
|---|---|
| Anthropic API | `anthropic/claude-opus-4-6` |
| Google Vertex AI (Claude) | `vertex_ai/claude-opus-4-6` |
| Amazon Bedrock | `bedrock/us.anthropic.claude-opus-4-6-v1` |
| OpenAI | `openai/gpt-5.4` |
| Gemini API | `gemini/gemini-3-pro-preview` |
| Azure OpenAI | `azure/<deployment-name>` |

Provider availability and deployment names depend on the account and region.
For a paper reproduction, record the resolved model version, provider, region,
and run date.

## Claude Code subscription

Install Claude Code, sign in on the host, and verify the session:

```bash
claude auth login
claude auth status

export CLAUDE_CODE_USE_SUBSCRIPTION=1
export CLAUDE_CODE_SUBSCRIPTION_MODEL="claude-opus-4-6"
```

Set `CLAUDE_CREDENTIALS_FILE` if Claude stores its credentials somewhere other
than `~/.claude/.credentials.json`.

Claude Code subscription can run released Skill-only evaluations and serve as
`GT_ORACLE_AGENT=claude-code-skill-only`. It does not supply the LiteLLM calls
used by `terminus-2-evolution`; `MODEL` and `VERIFIER_MODEL` still require a
separately configured API provider.

Do not enable Vertex AI or Bedrock in the same environment. The subscription
wrapper copies the host credential only into the short-lived oracle sandbox.

## Anthropic API

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
unset CLAUDE_CODE_USE_SUBSCRIPTION CLAUDE_CODE_USE_VERTEX CLAUDE_CODE_USE_BEDROCK
```

Use `MODEL=anthropic/<model-id>`.

## Google Vertex AI

First create Application Default Credentials:

```bash
gcloud auth application-default login
gcloud auth application-default print-access-token >/dev/null
```

For Claude on Vertex AI:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/application_default_credentials.json"
export ANTHROPIC_VERTEX_PROJECT_ID="your-gcp-project-id"
export CLOUD_ML_REGION="us-east5"
export VERTEXAI_LOCATION="us-east5"
export CLAUDE_CODE_USE_VERTEX=1
export ANTHROPIC_MODEL="claude-opus-4-6"
export ANTHROPIC_DEFAULT_OPUS_MODEL="claude-opus-4-6"
export ANTHROPIC_DEFAULT_SONNET_MODEL="claude-opus-4-6"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-opus-4-6"
export CLAUDE_CODE_SUBAGENT_MODEL="claude-opus-4-6"
```

For Gemini on Vertex AI:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GOOGLE_CLOUD_LOCATION="global"
```

## Amazon Bedrock

Enable model access in AWS and provide a bearer token or short-lived AWS
credentials. A host-only `AWS_PROFILE` is not automatically visible inside an
isolated task container.

```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION="us-east-2"
export AWS_BEARER_TOKEN_BEDROCK="your-bedrock-token"
export ANTHROPIC_MODEL="us.anthropic.claude-opus-4-6-v1"
```

Temporary access credentials can be supplied instead:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
```

Do not combine Bedrock with Vertex AI, Anthropic API, or Claude subscription
variables in the same run.

## Gemini Developer API

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

Use `MODEL=gemini/<model-id>` with `terminus-2-evolution`. A Gemini CLI oracle
uses `GT_ORACLE_AGENT=gemini-cli` and `GT_ORACLE_MODEL=google/<model-id>`.

## OpenAI API and Codex

For usage-based API access:

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

Use `MODEL=openai/<model-id>`. For a released Skill-only transfer run, set
`AGENT=codex-skill-only`. For an API-backed Codex oracle inside evolution, set
`GT_ORACLE_AGENT=codex-skill-only`.

For ChatGPT subscription authentication:

```bash
npm install -g @openai/codex
codex login
codex login status

export CODEX_CHATGPT_AUTH_FILE="$HOME/.codex/auth.json"
export CODEX_CLI_BINARY="$(command -v codex)"
export CODEX_REASONING_EFFORT="low"
```

For a released Skill-only transfer run:

```bash
export RUN_ID=codex-subscription-smoke

uv run python scripts/prepare_tasks.py \
  --condition skill-only \
  --skill-set validated \
  --tasks 3d-scan-calc

MODEL=openai/gpt-5.4 \
AGENT=codex-subscription \
MAX_PARALLEL=1 \
  scripts/run_condition.sh skill-only --only-tasks 3d-scan-calc
```

For a Codex subscription oracle inside evolution, set
`GT_ORACLE_AGENT=codex-subscription` and `GT_ORACLE_MODEL=openai/gpt-5.4`.
Choose a reasoning effort supported by the selected model. Model availability
can differ between ChatGPT subscription and API authentication, so verify the
selected model with a small canary before a benchmark-wide run.

## Other API-backed Agents

The `terminus-2` adapter can run released Skills with any model supported by
LiteLLM. First prepare the `skill-only` condition, export the provider's normal
credentials, and then use a provider-qualified model name:

```bash
export RUN_ID=other-agent-skill-only-smoke

uv run python scripts/prepare_tasks.py \
  --condition skill-only \
  --skill-set validated \
  --tasks 3d-scan-calc

MODEL=<provider>/<model-id> \
AGENT=terminus-2 \
MAX_PARALLEL=1 \
  scripts/run_condition.sh skill-only --only-tasks 3d-scan-calc
```

The prepared task contains the released Skill under
`/app/environment/skills/` and contains no background-document directory.

## Azure OpenAI

```bash
export AZURE_API_KEY="your-azure-openai-key"
export AZURE_API_BASE="https://your-resource.openai.azure.com"
export AZURE_API_VERSION="your-api-version"
```

Use `MODEL=azure/<deployment-name>` and the same value for `VERIFIER_MODEL`.
Azure OpenAI is supported for the generator and surrogate verifier through
LiteLLM. This release does not provide a built-in Azure OpenAI native
Skill-only oracle; pair it with a separately authenticated Claude Code or
Codex strict Skill-only oracle, or register a custom strict Skill-only Agent.

## Task-specific credentials

Agent authentication and task authentication are independent. Before a
benchmark-wide run, inspect the selected tasks' `task.toml` files and Docker
Compose definitions for declared environment variables. The most important
release case is:

| Task | Additional variable | Why it is needed |
|---|---|---|
| `pg-essay-to-audiobook` | `OPENAI_API_KEY` | Its canonical verifier evaluates the generated audio through an OpenAI-backed check. Without the key, the run has no valid canonical reward. |

Other media and causal-analysis tasks expose optional model credentials to
their runtime or reference workflow. Supply only credentials declared by the
tasks you select. Missing task infrastructure must be reported as an invalid
run, not as a Skill failure.

Credential values belong only in the ignored `.env` file or the host process
environment. They must never be copied into `artifacts/`, `workspaces/`, or
`outputs/`.

## Avoid provider conflicts

The runner reloads `.env` for worker processes. Remove inactive provider flags
from that file; unsetting a variable only in the parent shell is not enough if
`.env` sets it again.
