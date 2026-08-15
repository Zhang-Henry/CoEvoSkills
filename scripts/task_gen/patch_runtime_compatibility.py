#!/usr/bin/env python3
"""Apply task-specific runtime compatibility fixes to generated Dockerfiles."""

from __future__ import annotations

from pathlib import Path


SEISBENCH_INSTALL = "pip install --no-cache-dir seisbench==0.10.2"
SEISBENCH_COMPAT_INSTALL = (
    "pip install --no-cache-dir setuptools==80.9.0 seisbench==0.10.2"
)


def patch_dockerfile(path: Path, task_name: str) -> bool:
    """Patch known dependency incompatibilities. Returns True if modified."""
    if task_name != "seismic-phase-picking" or not path.exists():
        return False

    content = path.read_text()
    if SEISBENCH_COMPAT_INSTALL in content:
        return False
    if SEISBENCH_INSTALL not in content:
        raise RuntimeError(
            f"Expected SeisBench install command is missing from {path}"
        )

    explanation = (
        "# SeisBench 0.10.2 still imports pkg_resources. Newer setuptools "
        "releases no\n"
        "# longer provide it, so keep a compatible setuptools version in "
        "the image.\n"
    )
    content = content.replace(
        f"RUN {SEISBENCH_INSTALL}",
        f"{explanation}RUN {SEISBENCH_COMPAT_INSTALL}",
        1,
    )
    path.write_text(content)
    return True
