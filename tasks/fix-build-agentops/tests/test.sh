#!/bin/bash

# Use this file to install test dependencies and run the tests.
# It will be copied to /tests/test.sh and run from the working directory.

# Fail before running any task tests if a future image/preparation change has
# restored the paired passing artifact or an unrelated Git-history root. This
# mode permits commits created by the repair agent on top of the pinned failing
# baseline, so normal Git-based debugging remains valid.
if ! /usr/local/bin/assert-agentops-isolation --lineage; then
  mkdir -p /logs/verifier
  echo 0 > /logs/verifier/reward.txt
  exit 1
fi

export PATH="/root/.local/bin:/home/github/.local/bin:$PATH"
uv init --python 3.10
uv add pytest==8.4.1
uv add pytest-json-ctrf==0.3.5
uv add unidiff==0.7.5
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
unset PYTEST_ADDOPTS

# The passing-run script is verifier-only. Reuse the failed run's identical
# setup-python action bundle instead of keeping paired passing metadata in the
# agent image.
if [ ! -e /home/github/24653510459 ]; then
  ln -s /home/github/ci-runtime /home/github/24653510459
fi

.venv/bin/python -m pytest -c /dev/null --confcutdir=/tests -p no:cacheprovider -p ctrf --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA -v

PYTEST_EXIT_CODE=$?

if [ $PYTEST_EXIT_CODE -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi

# Copy artifacts (*.diff) for debugging
artifact_root="/logs/verifier/diffs"
failed_root="/home/github/build/failed"
repo_id="${REPO_ID:-}"

mkdir -p "$artifact_root"

if [ -n "$repo_id" ] && [ -d "$failed_root/$repo_id" ]; then
  dest_dir="$artifact_root/$repo_id"
  mkdir -p "$dest_dir"
  find "$failed_root/$repo_id" -maxdepth 1 -type f -name "patch_*.diff" -exec cp {} "$dest_dir"/ \;
elif [ -d "$failed_root" ]; then
  find "$failed_root" -type f -name "patch_*.diff" -exec cp {} "$artifact_root"/ \;
fi

# Copy failed reasons note for debugging
failed_note="$failed_root/failed_reasons.txt"
if [ -f "$failed_note" ]; then
  cp "$failed_note" /logs/verifier/failed_reasons.txt
fi
