# Java Build Debugging with Maven and Travis CI

This document provides background on diagnosing and fixing Java build failures in Maven-based projects that use Travis CI for continuous integration, with particular attention to the BugSwarm artifact structure and the unified diff format used for expressing code patches.

## Maven Build Lifecycle and POM Files

Apache Maven organizes builds into a well-defined lifecycle consisting of ordered phases. The phases most relevant to build debugging are:

- **validate** -- checks that the project descriptor (POM) is correct and all required information is available
- **compile** -- compiles the source code of the project
- **test-compile** -- compiles the test source code
- **test** -- runs unit tests using a suitable framework (typically JUnit or TestNG)
- **package** -- takes the compiled code and packages it (e.g., into a JAR)
- **verify** -- runs integration tests and any checks to ensure quality criteria are met
- **install** -- installs the package into the local repository for use as a dependency in other projects locally

When Maven is invoked with a phase name (e.g., `mvn verify`), it executes every phase in order up to and including the named phase. This means `mvn verify` will compile, test, package, and then run verification checks. Understanding this ordering is essential for diagnosing which phase actually failed.

### Multi-Module Builds and Custom POM Files

Large Java projects frequently use a multi-module structure, where a parent POM defines shared configuration and child modules provide individual components. Maven can be pointed at a specific POM file using the `-f` flag (for an unrelated synthetic example, `mvn -f ci-build.xml verify`). When debugging, discover the file referenced by the actual build entry point rather than copying a filename from this background.

### Common Maven Flags and Their Effects

- `-B` (batch mode): suppresses interactive prompts and produces output suitable for CI logs
- `-U` (update snapshots): forces Maven to check remote repositories for updated snapshot dependencies
- `-DskipTests=true`: compiles test code but does not execute tests
- `-Dsource.skip=true`: skips source JAR generation
- `-Dmaven.javadoc.skip=true`: skips Javadoc generation
- `--fail-at-end`: in multi-module builds, continues building remaining modules even if one fails, then reports all failures at the end
- `--fail-never`: never fails the build regardless of project errors (used during dependency resolution warmup phases)
- `--quiet`: suppresses all output except errors
- `-Dhttps.protocols=TLSv1.2`: restricts HTTPS connections to TLS 1.2, often needed for older JDK versions whose default TLS negotiation is incompatible with modern repository servers

### Diagnosing Maven Build Failures

Maven error output follows a predictable structure. A failed build will print:

1. A `[ERROR]` line identifying the failing module
2. The phase that failed (compilation, testing, etc.)
3. The specific plugin goal that raised the error (e.g., `maven-compiler-plugin:compile`)
4. A detailed error message, which for compilation errors includes the source file path, line number, and nature of the error

For compilation errors, the key details are always in the compiler output: the file path relative to the module root, the line and column of the error, and the diagnostic message. For test failures, Maven's Surefire plugin produces individual text reports under `target/surefire-reports/` in each module. For plugin execution errors, the stack trace identifies the plugin and its configuration.

When a build uses `--fail-at-end`, all module errors are collected and reported together at the end of the output. This means the first error logged may not be the root cause -- a compilation failure in a dependency module will cascade into "cannot find symbol" errors in downstream modules.

## JDK Version Compatibility

Java build failures are frequently caused by JDK version incompatibilities. Key considerations:

**Source and target levels**: Maven projects declare `maven.compiler.source` and `maven.compiler.target` properties (or equivalent plugin configuration) that specify which Java language version the code is written in and which bytecode version to emit. Code using features from a newer Java version than the configured source level will not compile.

**API availability**: Standard library APIs change between Java versions. Code that uses an API introduced in Java 8 will not compile under Java 7, even if the language features are compatible. Conversely, APIs deprecated in newer versions may still compile but produce warnings.

**Travis CI JDK switching**: Travis CI environments use `jdk_switcher` to select the active JDK. The `JAVA_HOME` and `PATH` environment variables are reconfigured when switching. Build scripts that hardcode JDK paths or assume a specific default can break when the JDK selection changes. The `jdk_switcher use <version>` command sets the active JDK for the remainder of the shell session.

**Annotation processing**: Projects that rely heavily on annotation processing (such as code generation frameworks) are particularly sensitive to JDK version changes, because the annotation processing and language model APIs evolved across Java versions, and processor implementations may depend on internal compiler APIs that change without notice.

## BugSwarm Artifact Structure

BugSwarm is a dataset of reproducible CI build failures. An artifact captures failing and passing repository states plus scripts or metadata that reproduce CI behavior. Directory layouts and which reference artifacts remain visible can vary, so inspect the current container rather than assuming paths or relying on access to a passing tree.

Available reproduction scripts are useful evidence for the JDK, Maven invocation, environment variables, and hooks that define the build contract. Identify the scripts that actually exist and run the relevant failing workflow. Do not use a hidden or reference solution tree as a source of the fix.

**Determine which configuration is authoritative.** Reproduction systems may use generated scripts, live repository CI files, or both. Trace the command that is actually executed before deciding which file can affect it. Preserve the task's modification scope and do not edit a runner merely to suppress a real failure.

### Working with the Build Environment

When analyzing a BugSwarm failure, the correct approach is:

1. Locate the repository state identified by the task as editable
2. Examine the available CI reproduction entry points to understand which commands, flags, and POM files the build uses
3. Attempt to reproduce the build failure by running the reproduction script to observe the exact error messages
4. Analyze the error output to identify root causes (compilation errors, missing dependencies, plugin failures, test failures)
5. Make minimal targeted fixes to the source code or project configuration
6. Verify fixes by re-running the same CI reproduction script to confirm the build passes end-to-end under the exact original conditions

The Maven local repository may contain cached dependencies, and a settings file may configure mirrors or authentication. Discover their actual locations from the environment and build scripts.

## Unified Diff Format

The unified diff format is the standard way to express textual changes to files. It is the format produced by `git diff` and consumed by `git apply`. A valid unified diff consists of one or more file patches. Each file patch begins with a pair of header lines: `--- a/path/to/original/file` and `+++ b/path/to/modified/file`. These are followed by one or more hunks, each introduced by a hunk header line of the form `@@ -start,count +start,count @@ optional context`. Within each hunk, lines prefixed with a single space are context (unchanged) lines, lines prefixed with `-` are deletions from the original, and lines prefixed with `+` are additions in the modified version.

**Header lines**: Each file patch begins with `---` (original) and `+++` (modified) lines specifying file paths. In git-style diffs, these are prefixed with `a/` and `b/`.

**Hunk headers**: Lines beginning with `@@` specify the line ranges in the original and modified files. The format is `@@ -original_start,original_count +modified_start,modified_count @@`. The counts indicate how many lines from each version appear in the hunk (including context lines).

**Content lines**: Within a hunk, lines prefixed with a space are context (unchanged), lines prefixed with `-` are deletions from the original, and lines prefixed with `+` are additions in the modified version. Every line in a hunk must have one of these three prefixes.

**Applying diffs**: `git apply` matches hunks to the target file using context lines. If the context does not match exactly (e.g., due to line number drift from other changes), the apply will fail. For this reason, diffs should include enough surrounding context (typically 3 lines) and be generated against the actual file state, not an assumed state.

### Producing Valid Diffs Programmatically

When writing diffs by hand or programmatically, common errors that produce invalid unified diffs include:

- Missing or malformed hunk headers (the `@@` lines)
- Incorrect line counts in hunk headers that do not match the actual number of context, addition, and deletion lines
- Missing the leading space on context lines (every unchanged line must start with exactly one space)
- Tabs or other whitespace instead of the required single-space prefix on context lines
- Missing the `---`/`+++` header pair for a file
- Including trailing whitespace that was not in the original file
- Using `\` no newline at end of file markers incorrectly

A diff file should be parseable by standard tools like GNU `patch`, `git apply`, and Python's `unidiff` library. If any of these reject the diff, it is malformed.

## Technical Considerations

**Root-cause analysis in multi-module builds**: In multi-module Maven builds, a compilation failure in one module cascades into dozens of "cannot find symbol" errors in dependent modules. Standard debugging methodology targets the original failing module by examining the earliest errors in the build log, rather than addressing downstream symptoms.

**Build command fidelity**: The build environment may use a non-default POM file (via `-f`), skip certain phases, or pass system properties that alter behavior. A fix that works under one Maven invocation may not succeed under a different invocation with specific flags. Standard practice is to test against the exact build invocation used in the CI script to ensure compatibility.

**File reference integrity**: As one item in a broader diagnosis, verify that paths referenced by the active build entry point resolve exactly. An unresolved path causes an early startup failure, while dependency, compilation, test, and plugin failures appear later. Let the observed error determine which category applies and choose the smallest in-scope fix; this background does not reveal the current artifact's root cause or replacement.

A systematic file-reference check is: extract path arguments from the active CI scripts and build configuration, verify every referenced file exists with an exact case-sensitive spelling, and inspect nearby similarly named files if a reference is unresolved. This is a general diagnostic; the current failure type and replacement path must be inferred from the actual logs and filesystem.

**JDK version awareness**: The build environment may use an older JDK than expected. Code that compiles under Java 8 may fail under Java 7 due to missing APIs, lambda expressions, or default methods in interfaces. Verifying which JDK the build script selects is a standard first step before assuming language features are available.

**Diff path alignment**: Diffs reference file paths relative to the correct root directory. The diff header specifies paths such as `a/src/main/java/Foo.java`, and these paths must match the actual repository layout relative to where the patch is applied. Path verification against the repository structure is an essential step in the patching workflow.

**Scope of build fixes**: When the task is to fix build errors in the code or configuration, the build script represents the CI contract -- the code must pass under the existing build configuration. The standard approach is to modify the source code or project configuration to satisfy the build requirements, rather than altering the build script to skip failing phases.

**Patch minimality**: Replacing entire files when only a few lines need to change makes the diff fragile and harder to verify. In professional practice, minimal, targeted patches that address only the specific error are preferred. Each patch should correspond to a single logical fix.
