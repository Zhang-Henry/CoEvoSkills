"""Self-verification — task-level evaluation of agent output via pytest scripts.

Runs an agent-created pytest script in the container.
If no script exists, returns a ``no_script`` result so the caller can
prompt the agent to generate one.
"""

from __future__ import annotations

import logging
import os
import re

from harbor.environments.base import BaseEnvironment

from .models import VerificationResult

logger = logging.getLogger(__name__)

# Paths to look for verifier scripts inside the container
_VERIFIER_SCRIPT_PATHS = [
    "/root/verifier/test_outputs.py",
    "/root/verifier/check_output.py",
]


class SelfVerifier:
    """Evaluate whether the agent successfully completed a task."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify(
        self,
        environment: BaseEnvironment,
    ) -> VerificationResult:
        """Run self-verification via agent-created pytest script.

        Returns a ``source="no_script"`` result when no verifier script is
        found, signalling the caller to prompt the agent to generate one.
        """
        script_path = await self._find_verifier_script(environment)

        if script_path:
            logger.info("Found verifier script at %s, running pytest", script_path)
            installed = await self._ensure_pytest(environment)
            if installed:
                result = await self._run_pytest(environment, script_path)
                if result.total_tests > 0:
                    return result
                logger.warning("Verifier script collected 0 tests (syntax error?)")
                return VerificationResult(
                    source="script_error",
                    reasoning=f"Verifier script exists at {script_path} but collected 0 tests (likely syntax error)",
                    raw_output=result.raw_output,
                )
            else:
                logger.warning("Failed to ensure pytest in container")

        return VerificationResult(
            source="no_script",
            reasoning="No verifier script found — agent must generate one",
        )

    # ------------------------------------------------------------------
    # Script-based verification
    # ------------------------------------------------------------------

    async def _find_verifier_script(self, environment: BaseEnvironment) -> str | None:
        """Check if a verifier pytest script exists in the container."""
        for path in _VERIFIER_SCRIPT_PATHS:
            result = await environment.exec(
                command=f"test -f '{path}' && echo EXISTS || echo MISSING",
                timeout_sec=10,
            )
            # stdout may contain shell warnings (e.g. "bash: cannot set terminal...")
            # so check if "EXISTS" appears anywhere, not just strict equality
            stdout = result.stdout or ""
            if "EXISTS" in stdout:
                return path
        return None

    async def _ensure_pytest(self, environment: BaseEnvironment) -> bool:
        """Ensure pytest is available in the container."""
        await environment.exec(
            command="python3 -m pytest --version 2>/dev/null || pip install --break-system-packages pytest 2>&1",
            timeout_sec=60,
        )
        # Verify it's actually available now
        check = await environment.exec(
            command="python3 -m pytest --version 2>&1",
            timeout_sec=10,
        )
        ok = check.return_code == 0
        if not ok:
            logger.warning("pytest installation check failed: %s", (check.stderr or check.stdout or "")[:200])
        return ok

    async def _run_pytest(self, environment: BaseEnvironment, script_path: str) -> VerificationResult:
        """Execute the pytest script and parse results."""
        # Media-heavy verifier suites (for example, ffmpeg/audio analysis) can
        # legitimately take several minutes.  Reuse the independent-verifier
        # budget instead of imposing a second hard-coded 120 second deadline
        # after the verifier agent has already completed the same test suite.
        timeout_sec = max(
            120,
            int(os.environ.get("INDEPENDENT_VERIFIER_TIMEOUT_SECONDS", "900")),
        )
        result = await environment.exec(
            command=f"python3 -m pytest '{script_path}' -v --tb=short 2>&1",
            timeout_sec=timeout_sec,
        )
        stdout = result.stdout or ""
        return self._parse_pytest_output(stdout, result.return_code)

    @staticmethod
    def _parse_pytest_output(stdout: str, return_code: int) -> VerificationResult:
        """Parse verbose pytest output into a VerificationResult."""
        test_details: list[dict] = []
        failure_reasons: list[str] = []

        # Extract individual test results from verbose output lines like:
        #   test_outputs.py::TestStructure::test_plan_length PASSED
        #   test_outputs.py::TestSolution::test_classification[some param with spaces] FAILED
        # Parametrized test names can contain spaces and special chars inside brackets,
        # so we match from the start of the test path to the status keyword at end of line.
        # Also handles the case where server stdout is interleaved between the test name and
        # PASSED/FAILED status (pytest -s), e.g.:
        #   ..::test_checkout_fast Analytics logged: {...}
        #   PASSED  [ 36%]
        # In this case we match the test name on one line and status on the next.
        test_line_re = re.compile(
            r"([\w./]+::[\w:]+(?:\[.*?\])?)\s+(PASSED|FAILED|ERROR|SKIPPED)(?:\s+\[\s*\d+%\s*\])?\s*$",
            re.MULTILINE,
        )
        # Secondary pattern: status word appears alone at start of line after interleaved output
        # We track the last-seen test name to associate it with a deferred status line.
        status_only_re = re.compile(
            r"^(PASSED|FAILED|ERROR|SKIPPED)(?:\s+\[\s*\d+%\s*\])?\s*$",
            re.MULTILINE,
        )
        # Build a map of position -> (full_name, status) for primary matches
        primary_matches: dict[int, tuple[str, str]] = {}
        for m in test_line_re.finditer(stdout):
            primary_matches[m.start()] = (m.group(1), m.group(2))

        # Find test name lines without immediate status (interleaved stdout case)
        # Pattern: test path at start of line followed by non-status content before EOL
        test_name_re = re.compile(
            r"^([\w./]+::[\w:]+(?:\[.*?\])?)\s+(?!PASSED|FAILED|ERROR|SKIPPED).*$",
            re.MULTILINE,
        )
        deferred: list[tuple[int, str]] = []  # (line_end_pos, full_name)
        for m in test_name_re.finditer(stdout):
            # Only consider if this position didn't already produce a primary match
            if m.start() not in primary_matches:
                deferred.append((m.end(), m.group(1)))

        # For each deferred test name, find the next status-only line
        extra_matches: list[tuple[str, str]] = []
        for pos, full_name in deferred:
            sm = status_only_re.search(stdout, pos)
            if sm:
                # Ensure no other test name appears between pos and this status line
                intervening = test_name_re.search(stdout, pos, sm.start())
                if not intervening:
                    extra_matches.append((full_name, sm.group(1)))

        all_matches: list[tuple[str, str]] = [(fn, st) for fn, st in primary_matches.values()] + extra_matches

        for full_name, status in all_matches:
            # Use the last part as the readable name
            short_name = full_name.split("::")[-1] if "::" in full_name else full_name
            test_details.append({"name": short_name, "full_name": full_name, "status": status, "message": ""})

        # Deduplicate test_details by full test path (keep first occurrence).
        # The regex matches both verbose result lines (e.g. "::test_foo PASSED")
        # and the FAILED summary section, causing duplicates.
        # IMPORTANT: Use full_name for dedup, not short_name — different test
        # classes can have methods with the same name (e.g. TestPR::test_total
        # vs TestIssue::test_total) and short_name dedup would incorrectly
        # merge them into one entry.
        seen_names: dict[str, int] = {}
        deduped: list[dict] = []
        for detail in test_details:
            key = detail.get("full_name", detail["name"])
            if key not in seen_names:
                seen_names[key] = len(deduped)
                deduped.append(detail)
            else:
                # If we already have this test but it was PASSED and now we see FAILED,
                # update to FAILED (the summary line is more authoritative)
                existing = deduped[seen_names[key]]
                if existing["status"] == "PASSED" and detail["status"] in ("FAILED", "ERROR"):
                    deduped[seen_names[key]] = detail
        test_details = deduped

        # Extract assertion error messages and match to failed tests
        # Pattern: FAILED test_path::name[params] - AssertionError: message
        # Also handles short traceback blocks with FAILED summary line
        assertion_re = re.compile(
            r"FAILED\s+([\w./]+::[\w:]+(?:\[.*?\])?)\s*[-\u2013]\s*(.*?)$",
            re.MULTILINE,
        )
        assertion_map: dict[str, str] = {}
        for m in assertion_re.finditer(stdout):
            full_name = m.group(1)
            short_name = full_name.split("::")[-1] if "::" in full_name else full_name
            assertion_map[short_name] = m.group(2).strip()

        # Extract AssertionError lines from traceback sections with line positions
        assert_error_re = re.compile(r"AssertionError:\s*(.+?)$", re.MULTILINE)
        assert_error_positions: list[tuple[int, str]] = []
        for m in assert_error_re.finditer(stdout):
            line_num = stdout[: m.start()].count("\n")
            assert_error_positions.append((line_num, m.group(1).strip()))

        # Build line-number map for test headers in the FAILURES section.
        # These headers (e.g. "_______ test_foo _______") appear immediately
        # above each test's traceback, so proximity matching against them
        # correctly associates each AssertionError with its owning test.
        # (Using the FAILED summary lines at the bottom would cause cross-
        # matching for 2+ failures because all summary lines cluster far
        # below the traceback assertions.)
        failure_header_re = re.compile(r"_{3,}\s+(.+?)\s+_{3,}\s*$", re.MULTILINE)
        failed_line_positions: dict[str, int] = {}
        for m in failure_header_re.finditer(stdout):
            raw_name = m.group(1).strip()
            short_name = raw_name.split("::")[-1] if "::" in raw_name else raw_name
            line_num = stdout[: m.start()].count("\n")
            failed_line_positions[short_name] = line_num

        # Match assertion messages to failed tests by proximity
        # Prefer full traceback messages (mechanism 2: assert_error_positions) over
        # truncated FAILED summary lines (mechanism 1: assertion_map).  pytest's
        # default 80-column terminal width truncates the summary to "A..." while
        # the --tb=short traceback contains the complete AssertionError message.
        failed_tests = [d for d in test_details if d["status"] == "FAILED"]
        used_assert_indices: set[int] = set()
        for detail in failed_tests:
            name = detail["name"]
            traceback_matched = False
            if assert_error_positions and name in failed_line_positions:
                # Find the closest assertion error by line number
                test_line = failed_line_positions[name]
                best_idx = min(
                    (i for i in range(len(assert_error_positions)) if i not in used_assert_indices),
                    key=lambda i: abs(assert_error_positions[i][0] - test_line),
                    default=None,
                )
                if best_idx is not None:
                    used_assert_indices.add(best_idx)
                    detail["message"] = assert_error_positions[best_idx][1]
                    traceback_matched = True
            if not traceback_matched and name in assertion_map:
                detail["message"] = assertion_map[name]

        # Build failure_reasons
        for detail in test_details:
            if detail["status"] in ("FAILED", "ERROR"):
                msg = detail.get("message", "")
                reason = f"{detail['name']}: {msg}" if msg else detail["name"]
                failure_reasons.append(reason)

        # Parse summary line: "3 passed, 2 failed" or "5 passed"
        # Skip "SKIPPED" tests — they are not applicable and should not inflate the denominator
        tests_passed = sum(1 for d in test_details if d["status"] == "PASSED")
        tests_failed = sum(1 for d in test_details if d["status"] in ("FAILED", "ERROR"))
        total_tests = tests_passed + tests_failed

        # Fallback: parse from summary line if we got no details
        if total_tests == 0:
            summary_re = re.compile(r"(\d+)\s+passed")
            failed_re = re.compile(r"(\d+)\s+failed")
            sm = summary_re.search(stdout)
            fm = failed_re.search(stdout)
            if sm:
                tests_passed = int(sm.group(1))
            if fm:
                tests_failed = int(fm.group(1))
            total_tests = tests_passed + tests_failed

        # Some benchmark verifiers are executable scripts rather than pytest
        # and emit a compact "FINAL SCORE: X/Y = Z" line.
        if total_tests == 0:
            final_score_matches = re.findall(
                r"FINAL SCORE:\s*(\d+)\s*/\s*(\d+)",
                stdout,
                flags=re.IGNORECASE,
            )
            if final_score_matches:
                passed_text, total_text = final_score_matches[-1]
                parsed_passed = int(passed_text)
                parsed_total = int(total_text)
                if parsed_total > 0 and parsed_passed <= parsed_total:
                    total_tests = parsed_total
                    tests_passed = parsed_passed
                    tests_failed = parsed_total - parsed_passed

        # A few other custom verifiers use a multiline summary.
        # Their stable summary format is:
        #   Total tests: 11
        #   Passed: 11
        #   Failed: 0
        # Parse the final summary block so successful custom verifiers are not
        # silently converted into 0/0 failures.
        if total_tests == 0:
            total_matches = re.findall(
                r"^\s*Total tests:\s*(\d+)\s*$", stdout, flags=re.IGNORECASE | re.MULTILINE
            )
            passed_matches = re.findall(
                r"^\s*Passed:\s*(\d+)\s*$", stdout, flags=re.IGNORECASE | re.MULTILINE
            )
            failed_matches = re.findall(
                r"^\s*Failed:\s*(\d+)\s*$", stdout, flags=re.IGNORECASE | re.MULTILINE
            )
            if total_matches and passed_matches:
                parsed_total = int(total_matches[-1])
                parsed_passed = int(passed_matches[-1])
                parsed_failed = (
                    int(failed_matches[-1])
                    if failed_matches
                    else max(0, parsed_total - parsed_passed)
                )
                if parsed_total > 0 and parsed_passed + parsed_failed <= parsed_total:
                    total_tests = parsed_total
                    tests_passed = parsed_passed
                    tests_failed = parsed_failed

        estimated_success = return_code == 0 and tests_failed == 0 and total_tests > 0

        return VerificationResult(
            estimated_success=estimated_success,
            failure_reasons=failure_reasons,
            reasoning=f"pytest: {tests_passed}/{total_tests} passed (pass_rate={tests_passed / total_tests if total_tests > 0 else 0.0:.2f}, return_code={return_code})",
            source="script",
            total_tests=total_tests,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            test_details=test_details,
            raw_output=stdout,
        )
