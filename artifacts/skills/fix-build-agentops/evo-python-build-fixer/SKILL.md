---
name: evo-python-build-fixer
description: "Diagnose and fix Python CI build failures in repositories using tox/pytest. Analyzes build logs, identifies root causes (version compatibility, logic errors, ordering bugs), generates unified diff patches, and applies fixes. Use when a task requires fixing errors in a Python codebase with CI build failures."
---

# Python Build Failure Fixer

This skill diagnoses and fixes Python CI build failures in repositories that use tox for test automation and pytest for testing.

## Workflow

1. **Discover** the repository structure and build configuration (tox.ini, pyproject.toml, CI workflows)
2. **Analyze** build logs to identify the first failing step and root cause
3. **Diagnose** the error category (version compatibility, logic bug, ordering issue)
4. **Fix** the source code with minimal targeted changes
5. **Generate** unified diff patch files
6. **Verify** by running the test suite

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-python-build-fixer/scripts')
from utils import (
    discover_repo,
    analyze_build_logs,
    find_source_files,
    check_version_compat_issues,
    write_analysis,
    create_patch_from_git_diff,
    verify_patch_applies,
    run_tests
)

# Step 1: Discover repo
repo_path, repo_name, repo_id = discover_repo('/home/github/build/failed')

# Step 2: Analyze build logs
logs = analyze_build_logs('/home/github/build')
print(f"Failure summary: {logs['summary']}")

# Step 3: Find and check source files
source_files = find_source_files(repo_path)
issues = check_version_compat_issues(source_files)

# Step 4: Write analysis
write_analysis('/home/github/build/failed/failed_reasons.txt', logs, issues)

# Step 5: After making fixes, create patch
create_patch_from_git_diff(repo_path, 1)  # Creates patch_1.diff

# Step 6: Verify
verify_patch_applies(repo_path, 1)
run_tests(repo_path)
```

## Common Failure Patterns

### 1. Timestamp/Ordering Logic Bugs
Methods that update state (like timestamps) after a guard clause that returns early.
The fix is to move the state update before the guard clause.

### 2. Python Version Compatibility
- `list[Type]` syntax (Python 3.9+) → use `List[Type]` from typing
- `dict[K,V]` syntax (Python 3.9+) → use `Dict[K,V]` from typing
- f-string enhancements (Python 3.12+)
- walrus operator `:=` (Python 3.8+)
- `match` statements (Python 3.10+)

### 3. Import Errors
- Missing dependencies in tox deps
- Module path changes between library versions

## Key Diagnostic Steps

1. Read the CI build logs first - they show the exact error
2. Look for the WARNING/ERROR lines and tracebacks
3. Identify which test environment failed (py37, py38, etc.)
4. Check if the error is in collection (import) or execution (assertion)
5. Make the minimal fix that preserves behavior
