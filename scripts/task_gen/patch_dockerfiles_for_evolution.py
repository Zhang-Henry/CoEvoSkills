#!/usr/bin/env python3
"""Patch Dockerfiles in a tasks directory to add evolution environment essentials.

Adds:
  1. pytest      — surrogate verifier runs agent-generated pytest scripts
  2. pyyaml      — skill-creator's quick_validate.py needs it

Usage:
    python3 scripts/task_gen/patch_dockerfiles_for_evolution.py workspaces/<RUN_ID>/evolution/
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Packages to inject
INJECT_PACKAGES = ["pytest", "pyyaml"]
EVOLUTION_MARKER = "Evolution essentials (surrogate verifier + skill validation)"


def _find_pip_block(content: str, require_bsp: bool = False) -> tuple[int, int] | None:
    """Find the last pip install block (start, end) character offsets.

    A pip install block is a RUN pip install line plus all continuation lines (ending with \\).
    If require_bsp, only match blocks containing --break-system-packages.
    """
    keyword = "--break-system-packages" if require_bsp else ""
    lines = content.split("\n")
    best_start = None
    best_end = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Match a pip install start line
        if re.match(r"RUN\s+pip3?\s+install\b", stripped) and (not keyword or keyword in stripped):
            start_line = i
            # Follow continuation lines
            while i < len(lines) and lines[i].rstrip().endswith("\\"):
                i += 1
            end_line = i  # last line of the block (no trailing \)
            best_start = start_line
            best_end = end_line
        i += 1

    if best_start is None:
        return None

    # Convert line indices to character offsets
    char_start = sum(len(lines[j]) + 1 for j in range(best_start))
    char_end = sum(len(lines[j]) + 1 for j in range(best_end + 1))
    # Don't include trailing newline in end
    if char_end > 0 and char_end <= len(content):
        char_end = char_end  # inclusive of the last line + newline
    return char_start, char_end


def _final_stage_start(content: str) -> int:
    """Return the character offset of the final Docker build stage."""
    matches = list(re.finditer(r"^FROM\s", content, re.MULTILINE | re.IGNORECASE))
    return matches[-1].start() if matches else 0


def _install_block(packages: list[str]) -> str:
    """Build a dependency layer that also bootstraps Python when necessary."""
    package_args = " ".join(packages)
    return (
        f"\n# {EVOLUTION_MARKER}\n"
        "RUN set -eu; \\\n"
        "    if command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then PYTHON_BIN=python3; \\\n"
        "    elif command -v python >/dev/null 2>&1 && python -m pip --version >/dev/null 2>&1; then PYTHON_BIN=python; \\\n"
        "    elif command -v apt-get >/dev/null 2>&1; then \\\n"
        "        apt-get update; \\\n"
        "        apt-get install -y --no-install-recommends python3 python3-pip; \\\n"
        "        rm -rf /var/lib/apt/lists/*; \\\n"
        "        PYTHON_BIN=python3; \\\n"
        "    else \\\n"
        "        echo 'Evolution dependencies require Python and pip' >&2; \\\n"
        "        exit 1; \\\n"
        "    fi; \\\n"
        f"    \"$PYTHON_BIN\" -m pip install --no-cache-dir --break-system-packages {package_args} 2>/dev/null || \\\n"
        f"    \"$PYTHON_BIN\" -m pip install --no-cache-dir {package_args}\n"
    )


def patch_dockerfile(path: Path) -> bool:
    """Patch a single Dockerfile. Returns True if modified."""
    content = path.read_text()
    original = content

    # Inject into the final stage only: build tools installed in an earlier
    # stage are not available to the agent at runtime.
    if EVOLUTION_MARKER not in content:
        stage_start = _final_stage_start(content)
        final_stage = content[stage_start:]
        missing = [pkg for pkg in INJECT_PACKAGES if pkg not in final_stage.lower()]
        if missing:
            install_block = _install_block(missing)
            workdir_match = re.search(r"^WORKDIR\s", final_stage, re.MULTILINE)
            insert_pos = stage_start + workdir_match.start() if workdir_match else len(content)
            content = content[:insert_pos] + install_block + "\n" + content[insert_pos:]

    if content != original:
        path.write_text(content)
        return True
    return False


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <tasks-dir>")
        sys.exit(1)

    tasks_dir = Path(sys.argv[1])
    if not tasks_dir.is_dir():
        print(f"ERROR: {tasks_dir} is not a directory")
        sys.exit(1)

    dockerfiles = sorted(tasks_dir.glob("*/environment/Dockerfile"))
    patched = 0
    skipped_no_python = 0
    for df in dockerfiles:
        content_lower = df.read_text().lower()
        if not any(tool in content_lower for tool in ("python", "pip", "apt-get")):
            skipped_no_python += 1
            continue
        if patch_dockerfile(df):
            task_name = df.parent.parent.name
            print(f"  patched: {task_name}")
            patched += 1

    print(f"\nPatched {patched}/{len(dockerfiles)} Dockerfiles ({skipped_no_python} skipped, no python)")


if __name__ == "__main__":
    main()
