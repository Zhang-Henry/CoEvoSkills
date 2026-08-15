---
name: evo-java-build-fixer
description: "Fix Java Maven build failures in CI environments. Handles tools.jar compatibility issues (Java 9+), dependency resolution errors, and generates proper unified diff patches. Use when tasked with fixing build errors in a Java/Maven repository."
---

# Java Build Fixer Skill

This skill diagnoses and fixes Java Maven build failures, particularly those caused by
Java version incompatibilities in CI environments (e.g., tools.jar missing in Java 9+).

## Workflow

1. **Discover** the repository under `/home/travis/build/failed/`
2. **Run** the build to capture error output
3. **Parse** Maven errors to identify root cause
4. **Analyze** dependency trees for problematic transitive dependencies
5. **Write** analysis to `failed_reasons.txt`
6. **Generate** minimal unified diff patches
7. **Apply** patches to fix the build
8. **Verify** the build passes

## Key Functions

- `find_repo_dir()` - Discovers the repository path
- `find_build_command()` - Extracts build command from .travis.yml
- `run_build()` - Executes the build and captures output
- `parse_maven_errors()` - Categorizes Maven error output
- `detect_tools_jar_issue()` - Identifies Java 9+ tools.jar problems
- `find_tools_jar_dependency_sources()` - Finds POMs with tools.jar dependencies
- `add_exclusion_to_dependency()` - Adds Maven exclusion blocks to POM dependencies
- `generate_diff()` - Creates proper unified diffs using the `diff` command
- `fix_tools_jar_issue()` - Generates patches for tools.jar problems
- `apply_patch()` - Applies patches using the `patch` command
- `run_end_to_end()` - Full pipeline from discovery to verification
- `validate_output()` - Validates all required output files exist and are correct

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-java-build-fixer/scripts')
from utils import run_end_to_end, validate_output

# Run the full pipeline
success = run_end_to_end(base_path='/home/travis/build/failed', build_timeout=300)
print(f"Build fix {'succeeded' if success else 'may need manual review'}")

# Validate outputs
valid = validate_output(base_path='/home/travis/build/failed')
print(f"Validation: {'PASS' if valid else 'FAIL'}")
```

## Common Build Failure Patterns

### tools.jar Missing (Java 9+)
Libraries like `compile-testing` depend on `com.sun:tools` with a system scope
pointing to `tools.jar`. In Java 9+, this file was removed. Fix by adding
`<exclusion>` blocks for `com.sun:tools` in the affected dependencies.

### Dependency Resolution
When Maven cannot resolve a dependency, check:
- Is the artifact available in configured repositories?
- Is a system-scoped dependency pointing to a valid path?
- Are profile activations correct for the current environment?

### Multi-Module Cascading Failures
In multi-module builds with `--fail-at-end`, fix the earliest failing module first.
Downstream "cannot find symbol" errors often resolve when the root module compiles.
