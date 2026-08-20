---
name: evo-python-build-fixer
description: "Fix Python build failures in CI environments. Analyzes tox/pytest failures, identifies version compatibility issues, dependency import errors, and test logic bugs. Produces analysis, diff patches, and applies fixes."
---

# Python Build Fixer Skill

This skill diagnoses and fixes Python build failures in CI environments,
particularly those using tox for multi-version testing and GitHub Actions.

## Workflow

1. **Discover** the repository structure and build configuration
2. **Reproduce** the build failure by running tox
3. **Analyze** error output to classify root causes
4. **Generate** minimal patches in unified diff format
5. **Apply** patches and verify fixes
6. **Validate** all required output artifacts exist

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-python-build-fixer/scripts')
from utils import discover_repo, analyze_build_failure, generate_patch, apply_patches, validate_outputs

# Step 1: Discover the repository
repo_path = discover_repo('/home/github/build/failed')

# Step 2: Analyze the build failure
analysis = analyze_build_failure(repo_path)

# Step 3: Write analysis
write_analysis(analysis, '/home/github/build/failed/failed_reasons.txt')

# Step 4: Generate and write patches
for i, fix in enumerate(analysis['fixes']):
    patch_content = generate_patch(repo_path, fix['file'], fix['original'], fix['replacement'])
    patch_path = f"{repo_path}/patch_{i+1}.diff"
    with open(patch_path, 'w') as f:
        f.write(patch_content)

# Step 5: Apply patches
apply_patches(repo_path)

# Step 6: Validate
validate_outputs(repo_path, '/home/github/build/failed/failed_reasons.txt')
```

## Common Error Patterns

### 1. Version Compatibility
- `importlib.metadata` (Python 3.8+)
- `list[Type]` built-in generics (Python 3.9+ at module level)
- `match` statements (Python 3.10+)
- `typing.TypeAlias` (Python 3.10+)
- f-string enhancements (Python 3.12+)

### 2. Dependency Migration
- `langchain.callbacks.base` moved to `langchain_core.callbacks.base`
- Other package reorganizations across major versions

### 3. Dataclass Default Issues
- `default_factory` setting values at creation time that should be set later
- Mutable default arguments

### 4. Diagnostic Strategy
- Run tox per-environment to isolate failures
- Check the first failing step in the pipeline
- Distinguish tox setup errors from pytest collection errors from test execution errors
- Correlate errors with Python version to identify compatibility issues
