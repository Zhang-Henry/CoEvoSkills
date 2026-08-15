"""Data models for the Skill Evolution system in terminus_agent."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Result of self-verification after task execution."""

    estimated_success: bool = False
    failure_reasons: list[str] = field(default_factory=list)
    reasoning: str = ""

    # Script-based verification fields
    source: str = "no_script"  # "script" | "no_script"
    total_tests: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    test_details: list[dict] = field(default_factory=list)
    # [{"name": "test_plan_length", "status": "PASSED"|"FAILED", "message": "Expected 7, got 5"}]
    raw_output: str = ""  # pytest stdout (truncated on serialization)
    error: str | None = None  # Infrastructure error (timeout, exception) — distinct from test failures
    diagnosis: str = ""  # Root-cause diagnosis for failed tests (from independent verifier)

    @property
    def pass_rate(self) -> float:
        """Continuous score: fraction of tests passed (0.0-1.0)."""
        if self.total_tests == 0:
            return 0.0
        return self.tests_passed / self.total_tests

    def to_dict(self) -> dict:
        return {
            "estimated_success": self.estimated_success,
            "pass_rate": self.pass_rate,
            "failure_reasons": self.failure_reasons,
            "reasoning": self.reasoning,
            "source": self.source,
            "total_tests": self.total_tests,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "test_details": self.test_details,
            "raw_output": self.raw_output[:2000],
            "error": self.error,
            "diagnosis": self.diagnosis[:3000],
        }
