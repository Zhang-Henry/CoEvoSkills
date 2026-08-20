#!/usr/bin/env bash

set -euo pipefail

repo=/home/github/build/failed/AgentOps-AI/agentops
runtime=/home/github/ci-runtime
failed_runner=/usr/local/bin/run_failed.sh
mode="${1:---lineage}"

fail() {
    echo "AgentOps isolation check failed: $*" >&2
    exit 1
}

[[ "$mode" == "--initial" || "$mode" == "--lineage" ]] || \
    fail "unsupported mode: $mode"
[[ -d "$repo/.git" ]] || fail "the failing checkout is not a Git repository"
[[ -d "$runtime/actions/actions-setup-python@v2" ]] || \
    fail "neutral CI action bundle is missing"
[[ -f "$runtime/event.json" ]] || fail "neutral CI event is missing"
[[ -x "$failed_runner" ]] || fail "failed-job runner is missing"
[[ ! -e /home/github/build/passed ]] || fail "paired passing checkout is present"
[[ ! -e /usr/local/bin/run_passed.sh ]] || fail "paired passing runner is present"

# No numeric BugSwarm run directory may survive in the Agent-visible image.
# This catches both the original failed run and any accidentally restored
# paired run without recording either lookup key in this checker.
if find /home/github -regextype posix-extended -mindepth 1 -maxdepth 1 \
    -type d -regex '/home/github/[0-9]+' -print -quit | grep -q .; then
    fail "numeric BugSwarm run directory is present"
fi

# The failed runner must use only the neutral action path and must derive the
# synthetic source identity from the isolated one-root checkout. A literal
# 40-hex GITHUB_SHA or numeric action path would reintroduce instance lookup
# metadata even if the corresponding directory had been renamed.
grep -Fq '/home/github/ci-runtime/' "$failed_runner" || \
    fail "failed-job runner does not use the neutral action path"
grep -Fq 'GITHUB_SHA=$TASK_SOURCE_SHA' "$failed_runner" || \
    fail "failed-job runner does not derive its source identity"
if grep -Eq '/home/github/[0-9]+' "$failed_runner"; then
    fail "failed-job runner contains a numeric BugSwarm action path"
fi
if grep -Eq 'GITHUB_SHA=[0-9a-f]{40}' "$failed_runner"; then
    fail "failed-job runner contains a literal upstream source SHA"
fi
if grep -Eq '"(id|tree_id)"[[:space:]]*:[[:space:]]*"[0-9a-f]{40}"' \
    "$runtime/event.json"; then
    fail "CI event contains an upstream commit or tree identifier"
fi

if find /home/github/build -maxdepth 1 -type f -name '*-orig.log' -print -quit | grep -q .; then
    fail "BugSwarm original run log is present"
fi
if find /home/github -maxdepth 3 \
    \( -iname '*passed*log*' -o -iname '*passing*log*' \) \
    -type f -print -quit | grep -q .; then
    fail "paired passing log is present"
fi

mapfile -t roots < <(git -C "$repo" rev-list --max-parents=0 --all)
[[ "${#roots[@]}" -eq 1 ]] || fail "expected exactly one Git-history root"
baseline="${roots[0]}"
[[ "$(git -C "$repo" show -s --format=%s "$baseline")" == \
    "Pinned failing baseline" ]] || fail "Git-history root is not the synthetic baseline"

# An alternate object database could make hidden reference objects readable
# even when this repository's own objects and refs appear clean.
[[ ! -s "$repo/.git/objects/info/alternates" ]] || \
    fail "alternate Git object database is configured"

if [[ "$mode" == "--initial" ]]; then
    [[ "$(git -C "$repo" rev-list --all --count)" == 1 ]] || \
        fail "initial image contains more than the pinned baseline commit"
    [[ "$(git -C "$repo" for-each-ref --format='%(refname)')" == refs/heads/main ]] || \
        fail "initial image contains unexpected Git refs"
    [[ -z "$(git -C "$repo" remote)" ]] || fail "initial image contains a Git remote"
    [[ -z "$(git -C "$repo" tag --list)" ]] || fail "initial image contains Git tags"
    if find "$repo/.git/logs" -type f -print -quit 2>/dev/null | grep -q .; then
        fail "initial image contains Git reflogs"
    fi
    if [[ -n "$(git -C "$repo" fsck --full --unreachable --no-reflogs 2>&1)" ]]; then
        fail "initial image contains unreachable Git objects"
    fi
fi
