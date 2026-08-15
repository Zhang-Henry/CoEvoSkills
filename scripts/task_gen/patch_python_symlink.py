#!/usr/bin/env python3
"""Patch Dockerfiles to add python -> python3 symlink.

Adds `RUN ln -sf /usr/bin/python3 /usr/bin/python` to Dockerfiles that use
Ubuntu or other non-python base images, so agents can use `python` instead
of `python3`.

Skips Dockerfiles based on `FROM python:*` (already have the symlink).

Usage:
    python3 scripts/task_gen/patch_python_symlink.py tasks/
    python3 scripts/task_gen/patch_python_symlink.py workspaces/<RUN_ID>/evolution/
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SYMLINK_LINE = "RUN ln -sf /usr/bin/python3 /usr/bin/python\n"
SYMLINK_MARKER = "ln -sf /usr/bin/python3 /usr/bin/python"


def _uses_python_base(content: str) -> bool:
    """Check if Dockerfile uses FROM python:* base image."""
    return bool(re.search(r"^FROM\s+python:", content, re.MULTILINE))


def _has_python3(content: str) -> bool:
    """Check if Dockerfile installs or uses python3."""
    lower = content.lower()
    return "python3" in lower or "python" in lower


def _find_apt_get_end(content: str) -> int | None:
    """Find the end of the first apt-get install block that includes python3."""
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r"RUN\s+apt-get\s+", stripped) and "install" in stripped:
            start = i
            # Follow continuation lines. Docker permits comment-only lines
            # inside a continued RUN instruction; they must not terminate the
            # block for insertion purposes.
            while i < len(lines):
                if lines[i].strip().startswith("#"):
                    i += 1
                    continue
                if lines[i].rstrip().endswith("\\"):
                    i += 1
                    continue
                break
            # Check if this block contains python3
            block = "\n".join(lines[start : i + 1])
            if "python3" in block.lower():
                # Return char offset after this block
                return sum(len(lines[j]) + 1 for j in range(i + 1))
        i += 1
    return None


def patch_dockerfile(path: Path) -> bool:
    """Patch a single Dockerfile. Returns True if modified."""
    content = path.read_text()

    # Skip if already has the symlink
    if SYMLINK_MARKER in content:
        return False

    # Skip FROM python:* images (already have python command)
    if _uses_python_base(content):
        return False

    # Skip if no python at all
    if not _has_python3(content):
        return False

    # Try to insert after apt-get install block that has python3
    insert_pos = _find_apt_get_end(content)
    if insert_pos is not None:
        content = content[:insert_pos] + SYMLINK_LINE + content[insert_pos:]
    else:
        # Fallback: insert before first WORKDIR
        workdir_match = re.search(r"^WORKDIR\s", content, re.MULTILINE)
        if workdir_match:
            content = content[: workdir_match.start()] + SYMLINK_LINE + "\n" + content[workdir_match.start() :]
        else:
            # Last resort: append
            content += "\n" + SYMLINK_LINE

    path.write_text(content)
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <tasks-dir> [<tasks-dir2> ...]")
        sys.exit(1)

    total_patched = 0
    total_skipped_python_base = 0
    total_skipped_no_python = 0
    total_skipped_exists = 0

    for tasks_dir_arg in sys.argv[1:]:
        tasks_dir = Path(tasks_dir_arg)
        if not tasks_dir.is_dir():
            print(f"WARNING: {tasks_dir} is not a directory, skipping")
            continue

        print(f"\nProcessing: {tasks_dir}")
        dockerfiles = sorted(tasks_dir.glob("*/environment/Dockerfile"))

        for df in dockerfiles:
            content = df.read_text()
            task_name = df.parent.parent.name

            if SYMLINK_MARKER in content:
                total_skipped_exists += 1
                continue
            if _uses_python_base(content):
                total_skipped_python_base += 1
                continue
            if not _has_python3(content):
                total_skipped_no_python += 1
                continue

            if patch_dockerfile(df):
                print(f"  patched: {task_name}")
                total_patched += 1

    print(f"\nDone: {total_patched} patched, "
          f"{total_skipped_python_base} skipped (python base), "
          f"{total_skipped_no_python} skipped (no python), "
          f"{total_skipped_exists} skipped (already patched)")


if __name__ == "__main__":
    main()
