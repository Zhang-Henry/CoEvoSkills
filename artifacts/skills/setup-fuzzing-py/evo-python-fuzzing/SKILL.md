---
name: evo-python-fuzzing
description: "Set up coverage-guided fuzzing for Python libraries using Atheris and libFuzzer. Discovers libraries, analyzes fuzz targets, generates fuzz drivers, creates virtual environments, runs fuzzers, and validates results."
---

# Python Coverage-Guided Fuzzing Skill

This skill automates the setup and execution of coverage-guided fuzzing for
Python libraries using Atheris (Google's Python fuzzing engine backed by libFuzzer).

## Workflow

1. **Discover** Python libraries in a base directory
2. **Analyze** each library to find good fuzz targets (parsers, deserializers, formatters)
3. **Generate** notes_for_testing.txt with analysis results
4. **Generate** fuzz.py drivers with proper Atheris instrumentation
5. **Setup** virtual environments with dependencies
6. **Run** fuzzers with time budget and capture logs
7. **Validate** fuzz logs for successful completion

## Key Concepts

- Atheris bridges Python to libFuzzer for coverage-guided fuzzing
- Fuzz drivers must instrument target imports before calling them
- TestOneInput accepts bytes, uses FuzzedDataProvider for structured data
- libFuzzer output goes to stderr; capture it for the log
- Good targets: parsers, deserializers, formatters accepting string/bytes input
- For large libraries, import only the specific submodule to avoid slow startup
- Catch expected exceptions so fuzzer only reports unexpected crashes

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-python-fuzzing/scripts')
from utils import run_all, validate_all

# End-to-end: discover, analyze, generate, setup, fuzz, validate
results = run_all(
    base_dir='/app',
    libraries_file='/app/libraries.txt',
    timeout=10
)

# Validate all artifacts exist and logs are valid
all_ok = validate_all('/app', '/app/libraries.txt')
print(f"All OK: {all_ok}")
```

## Individual Functions

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-python-fuzzing/scripts')
from utils import (
    discover_libraries,
    write_libraries_file,
    analyze_library,
    generate_notes,
    write_notes,
    generate_fuzz_driver,
    write_fuzz_driver,
    setup_venv,
    run_fuzzer,
    validate_fuzz_log,
)

# Step 1: Discover libraries
libs = discover_libraries('/app')
write_libraries_file(libs, '/app/libraries.txt')

# Step 2: Analyze and write notes
for lib_path in libs:
    info = analyze_library(lib_path)
    notes = generate_notes(info)
    write_notes(lib_path, notes)

# Step 3: Generate fuzz drivers
for lib_path in libs:
    info = analyze_library(lib_path)
    driver = generate_fuzz_driver(info)
    write_fuzz_driver(lib_path, driver)

# Step 4: Setup virtual environments
for lib_path in libs:
    setup_venv(lib_path)

# Step 5: Run fuzzers
for lib_path in libs:
    success, log = run_fuzzer(lib_path, timeout=10)
    validation = validate_fuzz_log(f"{lib_path}/fuzz.log")
```

## Fuzz Driver Structure

Generated fuzz drivers follow this pattern:

```python
import sys
import atheris

# Instrument target library imports
with atheris.instrument_imports():
    import target_library

@atheris.instrument_func
def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    s = fdp.ConsumeUnicodeNoSurrogates(512)
    try:
        target_library.parse(s)
    except (ValueError, TypeError):
        pass
    except Exception:
        pass

def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()

if __name__ == "__main__":
    main()
```

## Validation Checks

- libraries.txt exists with valid library paths
- Each library has notes_for_testing.txt, fuzz.py, fuzz.log
- Each library has .venv/bin/python
- fuzz.log contains "Done N runs in M second(s)" completion marker
- Coverage progression visible in log (INITED, NEW, DONE markers)
