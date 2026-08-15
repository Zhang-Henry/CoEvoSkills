# Coverage-Guided Fuzzing for Python with Atheris and libFuzzer

## Core Concept

Coverage-guided fuzzing feeds semi-random inputs to a program and uses code coverage feedback to steer mutation toward inputs that exercise new code paths. The loop is: maintain a corpus of interesting inputs, mutate one, execute the fuzz target, measure which code paths were traversed, and add the input to the corpus if it triggered new coverage. This continues until a time/iteration budget is exhausted or a crash is found.

## Atheris Architecture

Atheris is Google's coverage-guided Python fuzzing engine, bridging Python code to **libFuzzer** (the industry-standard C/C++ fuzzing engine).

- **libFuzzer** (C/C++ layer): mutation engine, corpus management, coverage tracking, main fuzzing loop. Controlled by flags like `-max_total_time=10` (seconds) or `-runs=3` (iterations).
- **Atheris** (Python layer): setup/entry points, Python-level instrumentation, bridges Python functions to the libFuzzer engine.

## Fuzz Driver Structure

Every Atheris fuzz driver must contain these elements:

1. **Fuzz target function**: conventionally named `TestOneInput`, accepts a single `bytes` argument. Called once per fuzzing iteration.
2. **FuzzedDataProvider**: converts raw bytes into structured data (strings, integers, floats, booleans, byte sequences) deterministically.
3. **Instrumentation activation**: must happen **before** importing the target library modules.
4. **Setup call**: registers the fuzz target and passes command-line arguments (libFuzzer flags) through to libFuzzer.
5. **Fuzz loop initiation**: explicitly starts the fuzzing loop. Without this call, the script exits immediately with no fuzzing performed. The loop call (`atheris.Fuzz()`) does not return until the fuzzer finishes.

The fuzz target should catch **expected** exceptions (e.g., ValueError for malformed dates, JSON decode errors) so the fuzzer only reports truly unexpected failures. Broad exception catching is acceptable when the library's exception hierarchy is unclear. The fuzz target should be stateless -- avoid file writes, global state mutation, or accumulating side effects across iterations.

## Instrumentation

Instrumentation is how the fuzzer observes which code paths are executed. Without it, coverage-guided fuzzing degrades to random testing.

Atheris provides three approaches:

- **Global instrumentation**: instruments the Python functions that are already loaded when `instrument_all()` is called. Put it after the relevant Python modules have been imported and immediately before the setup step. It does not retroactively instrument native machine code inside a compiled extension.
- **Import-scoped instrumentation**: a context manager that instruments Python modules imported within its block. Useful for targeted instrumentation of specific libraries; place the target import inside the context.
- **Per-function instrumentation**: a decorator for a specific Python function. Decorating the fuzz-target function itself provides a small, dependable Python coverage surface even when the called API is implemented in native code or rejects the first inputs before reaching instrumented target-library code.

Instrumentation order depends on the chosen mechanism. For import-scoped instrumentation, activate the context before importing the target module. For global instrumentation, first import the Python modules whose existing functions should be instrumented, then call `instrument_all()` before `Setup`. A robust driver may also decorate its fuzz-target function explicitly. After writing the driver, run a very small smoke test and confirm that mutation produces observable coverage events; a process that merely stays alive for the allotted time is not necessarily coverage-guided.

## Recognizing a Successful Fuzzing Run

A correctly set up fuzzing run produces specific markers in the log output (written to **stderr**, not stdout):

**Instrumentation indicators**: inspect startup output and early coverage events to confirm that target-library code is instrumented. A run with no observable target coverage warrants checking import order and instrumentation, but do not rely on one benchmark-specific warning string.

**Coverage progression**: a healthy run shows:
- `INITED cov: <N>` -- fuzzer initialized with starting coverage
- `NEW cov: <N>` -- new input found that increased coverage
- `pulse cov: <N>` -- periodic status updates

**Normal completion**: the log ends with a line like `Done 13566 runs in 10 second(s)` when the budget is exhausted.

**Crash finding**: if the fuzzer discovers a crash, the log contains a fatal-signal diagnostic and reports a generated reproducer artifact. A crash is a **successful finding**, not a setup error. When a crash occurs, the ordinary budget-exhaustion completion line is not printed.

## Choosing Functions to Fuzz

Best candidates:
- **Parsers and deserializers**: functions accepting complex structured input (JSON, date/time strings, code to format). Large input spaces, historically rich in bugs.
- **Functions with complex control flow**: many branches, error-handling paths, or state machines.
- **Public API entry points**: most likely to receive untrusted input in real usage.

Poor candidates: pure mathematical functions with simple inputs, I/O-bound functions, functions requiring complex stateful setup (database connections, network sockets, GPU contexts).

### Finding a Fuzz Target Quickly

When examining an unfamiliar library, use these signals to locate a good entry point without exhaustive exploration:

- **Read `__init__.py`**: the public API is re-exported there. Focus on functions that accept `str`, `bytes`, or `dict` arguments.
- **Look for parse/load/decode/format names**: functions with these verbs are almost always parser entry points and the highest-value fuzzing targets.
- **Check existing tests**: the library's own test files show which functions are called with string or bytes inputs — these are already known-good call patterns to adapt for fuzzing.
- **Prefer shallow entry points**: a top-level function that accepts raw input and delegates internally is better than deep internal helpers that require complex state to set up.

The goal is to identify one concrete callable per library quickly — not an exhaustive analysis of the entire codebase.

## Environment Setup

### Environment-Driven Workflow

Inspect each target library before choosing setup commands: check its `pyproject.toml`, requirements files, supported Python versions, native build dependencies, and the package managers actually present. Create an isolated environment, install the project and Atheris into that environment, and invoke the fuzz driver through the project's supported runner. Do not assume a particular Python version, command-line flag, prebuilt wheel, or validator invocation from this background.

After setup, verify from inside the selected environment that both the target package and Atheris import successfully. Capture the fuzzer's stderr in the requested log and use the task instruction—not a hidden test command—to determine filenames and execution contracts.

### Library Listing File

Follow the task instruction's requested path representation. Discover the
library directories at runtime, write one unambiguous entry per library, and
verify that each entry resolves to the intended directory from the location
where the list will be consumed. Do not copy library names or a path convention
from an example background document.

### Handling Difficult Libraries

Some libraries have native extensions or specialized dependencies that make installation difficult. Diagnose missing toolchains and inspect pure-Python entry points where appropriate, while still satisfying the explicit artifact and execution requirements. Do not create placeholder environments or drivers that never exercise the target library.

### Importing the Target Library in the Fuzz Driver

Each fuzz driver must import and call the actual target library's API within the instrumented scope. A driver that only exercises Python standard library modules provides no coverage of the target. Identify at least one concrete entry point — a parsing function, formatter, or data constructor — and call it with fuzz-generated input inside `TestOneInput`.

For large libraries with slow initialization (e.g., interactive shells or frameworks that load many subsystems on import), importing the full top-level package can cause the fuzz driver startup to exceed time limits. In these cases, import only the specific submodule containing the target function rather than the full package. This keeps startup fast and instrumentation focused.

### Concurrent Library Processing

Independent libraries may be processed concurrently when CPU, memory, disk, and package-manager locking allow it. Bound concurrency from observed resources and failure behavior; no fixed library count or required scheduling pattern is supplied here.

### Running and Logging

libFuzzer writes all operational output to **stderr**. Capturing the fuzzing log requires redirecting stderr to a file; redirecting stdout alone produces an empty log.
