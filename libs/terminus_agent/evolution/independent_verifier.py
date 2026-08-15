"""Independent verifier — generates and runs surrogate verification in isolation.

Uses a separate LLM session (no shared context with the evolution agent) to
generate pytest scripts based solely on the task instruction, environment files,
and output files.  Eliminates confirmation bias by preventing the verifier from
seeing the evolution agent's implementation code or reasoning.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from libs.terminus_agent.agents.terminus_2.skill_docs import SkillDocLoader

from .models import VerificationResult
from .self_verifier import SelfVerifier

logger = logging.getLogger(__name__)


class IndependentVerifier:
    """Generate and run a surrogate verifier using an independent LLM session.

    The verifier agent runs inside the *same* Docker container as the evolution
    agent (so it can read output files), but uses a completely separate LLM
    session with its own prompt template — no context pollution from
    implementation details.

    Workflow per invocation:
    1. Spin up a fresh ``HarborTerminus2WithSkills`` agent with the independent
       verifier prompt template.
    2. The agent autonomously discovers files, writes pytest tests, runs them,
       and signals task_complete.
    3. ``SelfVerifier.verify()`` reads the generated test results.
    """

    def __init__(self, model_name: str, temperature: float = 0.3):
        self._model_name = model_name
        self._temperature = temperature
        self._timeout_sec = max(
            900,
            int(os.environ.get("INDEPENDENT_VERIFIER_TIMEOUT_SECONDS", "900")),
        )
        self._diagnosis_timeout_sec = max(
            900,
            int(os.environ.get("DIAGNOSIS_VERIFIER_TIMEOUT_SECONDS", "900")),
        )
        self._generation_count: int = 0
        self._last_result: VerificationResult | None = None

    async def generate_and_run(
        self,
        environment: BaseEnvironment,
        instruction: str,
        logs_dir: Path,
        *,
        adversarial_recheck: bool = False,
    ) -> VerificationResult:
        """Launch an independent verifier agent, then read pytest results.

        The agent runs in the same container as the evolution agent (shared
        output files) but with a fresh LLM session and verification-only prompt.
        """
        # Lazy import to avoid circular dependency (evolution -> skills -> evolution)
        from libs.terminus_agent.agents.terminus_2.harbor_terminus_2_skills import (
            HarborTerminus2WithSkills,
        )

        self._generation_count += 1

        verifier_logs = logs_dir / f"independent-verifier-{self._generation_count}"
        verifier_logs.mkdir(parents=True, exist_ok=True)

        prompt_template_path = Path(__file__).parent / "prompt_templates" / "independent_verifier.txt"

        # Delete per-session progress files and previous diagnosis; keep the verifier script for inheritance
        await environment.exec(
            command="rm -f /root/verifier_progress.md /root/verifier_requirements.txt /root/verifier/diagnosis.md",
            timeout_sec=10,
        )

        # Read existing verifier script (if any) for inheritance context
        previous_verifier_context = await self._build_previous_verifier_context(
            environment,
            adversarial_recheck=adversarial_recheck,
        )

        # Create a minimal agent: fresh LLM session, verifier prompt, no skill loading
        verifier_agent = HarborTerminus2WithSkills(
            logs_dir=verifier_logs,
            model_name=self._model_name,
            temperature=self._temperature,
            prompt_template=str(prompt_template_path),
            # Opus can spend several turns on file discovery before writing the
            # verifier. Keep enough room to produce, run, and repair a script;
            # the prompt separately requires a runnable script by turn six.
            max_episodes=30,
        )
        # Minimal setup: ensure python3, initialize skill loader (needed by
        # _check_for_new_skills in run loop) but skip full index build
        await verifier_agent._ensure_python3_installed(environment)
        public_doc_sources = await self._read_public_doc_sources(environment)
        verifier_agent._skill_loader = SkillDocLoader(environment=environment)
        raw_template = prompt_template_path.read_text(encoding="utf-8")
        # Escape braces in previous_verifier_context so they survive str.format()
        # in run() — the context often contains Python scripts with dict literals
        # and f-strings that would otherwise be interpreted as format placeholders.
        safe_context = previous_verifier_context.replace("{", "{{").replace("}", "}}")
        verifier_agent._prompt_template = raw_template.replace("{previous_verifier_context}", safe_context)

        logger.info(
            "Starting independent verifier agent (generation #%d, model=%s)",
            self._generation_count,
            self._model_name,
        )

        agent_error: str | None = None
        try:
            await asyncio.wait_for(
                verifier_agent.run(instruction, environment, AgentContext()),
                timeout=self._timeout_sec,
            )
        except TimeoutError:
            agent_error = (
                "Independent verifier agent timed out after "
                f"{self._timeout_sec}s"
            )
            logger.warning(agent_error)
        except Exception as exc:
            agent_error = f"Independent verifier agent failed: {exc}"
            logger.warning(agent_error)

        boundary_violations = self._audit_verifier_logs(verifier_logs)
        coordinate_violations = self._audit_structured_coordinate_methodology(
            verifier_logs,
            instruction,
            public_doc_sources,
        )
        verifier_violations = boundary_violations + coordinate_violations
        if verifier_violations:
            details = "; ".join(verifier_violations[:5])
            if coordinate_violations and not boundary_violations:
                agent_error = (
                    "Independent verifier violated structured-coordinate "
                    f"methodology: {details}"
                )
            else:
                agent_error = (
                    "Independent verifier violated verification boundary: "
                    f"{details}"
                )
            logger.warning(agent_error)

        # Read the test results written by the agent (may have partially succeeded)
        self_verifier = SelfVerifier()
        result = await self_verifier.verify(environment=environment)

        if verifier_violations:
            # A verifier that inspected candidate-generation internals or invoked
            # the production pipeline is not independent. A structured-coordinate
            # verifier that inspects the current artifact before proving its public
            # parity convention is likewise methodologically invalid. Even if its
            # pytest happens to pass, force the caller down the infrastructure-retry
            # path and never feed its diagnosis back into evolution.
            result.source = "script_error"
            result.error = agent_error
            result.estimated_success = False
            result.failure_reasons.append(agent_error or "Verifier boundary violation")

        # Read diagnosis file (written by V8 step for failed tests)
        result.diagnosis = await self._read_diagnosis(environment)
        if verifier_violations:
            # Discard the whole invalid IV round. In particular, do not let a later
            # generation inherit its current-instance tests or diagnosis and do not
            # expose any discovered failure to the evolution worker.
            result.diagnosis = ""
            await environment.exec(
                command=(
                    "rm -f /root/verifier/test_outputs.py "
                    "/root/verifier/diagnosis.md "
                    "/root/verifier_progress.md "
                    "/root/verifier_requirements.txt"
                ),
                timeout_sec=10,
            )

        self._last_result = result  # Store for next invocation's context

        # Always propagate infrastructure errors so the caller knows the verifier
        # had issues, even if a partial script was produced before the crash/timeout.
        if agent_error:
            result.error = agent_error
            if result.source in ("no_script", "script_error"):
                logger.warning("Verifier infrastructure failure, no usable script produced (source=%s): %s", result.source, agent_error)
            else:
                logger.warning(
                    "Verifier infrastructure failure but partial script found (%d tests). Results may be incomplete: %s",
                    result.total_tests,
                    agent_error,
                )
        else:
            logger.info(
                "Independent verifier completed: source=%s, tests=%d passed / %d total",
                result.source,
                result.tests_passed,
                result.total_tests,
            )

        return result

    @staticmethod
    def _audit_verifier_logs(verifier_logs: Path) -> list[str]:
        """Reject verifier sessions that inspect or execute candidate internals."""
        forbidden = {
            "/app/environment/skills": "inspected candidate Skill files",
            "/root/evolution_summary.md": "inspected evolution summary",
            "/root/progress.md": "inspected candidate progress",
            "/root/run.py": "invoked candidate run script",
            "from run_pipeline import": "imported candidate pipeline",
            "from pipeline import run_pipeline": "imported candidate pipeline",
            "run_pipeline(": "invoked candidate pipeline",
        }
        violations: list[str] = []
        for response_path in sorted(verifier_logs.glob("episode-*/response.txt")):
            try:
                response = response_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # A verifier may enumerate public environment files while explicitly
            # excluding the candidate Skill tree.  Merely naming the root in the
            # canonical ``find ... -path ROOT -prune`` exclusion is not an
            # inspection.  Remove only that exact exclusion clause before the
            # marker audit; any second occurrence (cat/ls/find/import/invoke, or a
            # path below the root) remains visible and is still rejected.
            audited_response = re.sub(
                r"-path\s+(?:"
                r"/app/environment/skills|"
                r"'/app/environment/skills'|"
                r'\"/app/environment/skills\"|'
                r'\\\"/app/environment/skills\\\"'
                r")\s+-prune\b",
                "-path __SKILL_PRUNED_ROOT__ -prune",
                response,
            )
            for marker, reason in forbidden.items():
                if marker in audited_response:
                    violations.append(f"{response_path.parent.name}: {reason}")
        return violations

    @staticmethod
    async def _read_public_doc_sources(
        environment: BaseEnvironment,
    ) -> tuple[str, ...]:
        """Read authoritative background documents without mixing in verifier prompts.

        Coordinate-method applicability must be established by the public task
        contract itself.  Verifier prompts contain generic examples for many
        unrelated task families, so using their transcript for applicability
        can combine unrelated keywords into a false positive.
        """

        begin_marker = "__SKILL_PUBLIC_DOCS_BEGIN__"
        end_marker = "__SKILL_PUBLIC_DOCS_END__"
        try:
            result = await environment.exec(
                command=(
                    "python3 - <<'PY'\n"
                    "import json\n"
                    "from pathlib import Path\n"
                    "root = Path('/app/environment/doc')\n"
                    "docs = []\n"
                    "if root.is_dir():\n"
                    "    for path in sorted(root.rglob('*')):\n"
                    "        if path.is_file():\n"
                    "            try:\n"
                    "                docs.append(path.read_text(encoding='utf-8', errors='replace'))\n"
                    "            except OSError:\n"
                    "                pass\n"
                    f"print('{begin_marker}')\n"
                    "print(json.dumps(docs))\n"
                    f"print('{end_marker}')\n"
                    "PY"
                ),
                timeout_sec=10,
            )
            raw_output = result.stdout if result.stdout else ""
            if begin_marker not in raw_output or end_marker not in raw_output:
                return ()
            payload = raw_output.split(begin_marker, 1)[1].split(end_marker, 1)[0]
            decoded = json.loads(payload.strip())
            if not isinstance(decoded, list):
                return ()
            return tuple(item for item in decoded if isinstance(item, str))
        except Exception:
            logger.warning(
                "Could not read authoritative background documents for coordinate-method scope",
                exc_info=True,
            )
            return ()

    @staticmethod
    def _audit_structured_coordinate_methodology(
        verifier_logs: Path,
        instruction: str,
        public_doc_sources: tuple[str, ...] = (),
    ) -> list[str]:
        """Reject parity-sensitive coordinate verifiers with unproven geometry.

        The public coordinate convention may live in a background document rather than the
        short task instruction. Applicability is therefore derived only from
        the instruction and host-read public docs, never from the verifier's
        generic prompt or response transcript. For an odd/even offset
        convention, the verifier must run a synthetic neighbor-and-distance
        parity check before it reads any current input or output artifact, emit
        the success marker, and persist the same invariant as a pytest test.
        This ordering prevents current coordinates from being used to
        rationalize a familiar but incorrect row/column convention.
        """

        def episode_number(path: Path) -> int:
            match = re.search(r"episode-(\d+)", path.parent.name)
            return int(match.group(1)) if match else 10**9

        parity_markers = (
            "odd-row",
            "odd row",
            "odd-r",
            "even-row",
            "even row",
            "even-r",
            "odd-column",
            "odd column",
            "odd-q",
            "even-column",
            "even column",
            "even-q",
        )
        coordinate_markers = (
            "hex grid",
            "hex neighbor",
            "offset coordinate",
            "structured map",
            "tile coordinate",
            "spatial relationship",
        )

        authoritative_sources = (instruction, *public_doc_sources)
        structured_coordinate_contract = any(
            any(marker in source.lower() for marker in parity_markers)
            and any(marker in source.lower() for marker in coordinate_markers)
            for source in authoritative_sources
        )
        if not structured_coordinate_contract:
            return []

        command_stream: list[tuple[int, int, str]] = []
        response_paths = sorted(
            verifier_logs.glob("episode-*/response.txt"),
            key=episode_number,
        )
        for response_path in response_paths:
            try:
                raw = response_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = None
            commands = payload.get("commands", []) if isinstance(payload, dict) else []
            if isinstance(commands, list):
                for command_index, command in enumerate(commands):
                    if isinstance(command, dict):
                        keystrokes = command.get("keystrokes", "")
                        if isinstance(keystrokes, str):
                            command_stream.append(
                                (episode_number(response_path), command_index, keystrokes)
                            )

        def is_current_artifact_inspection(command: str) -> bool:
            lowered = command.lower()
            if not re.search(r"/(?:data|output)/", lowered):
                return False
            return bool(
                re.search(
                    r"\b(?:cat|sed|head|tail|jq|sqlite3)\b|"
                    r"(?:open|read_text|json\.load|sqlite3\.connect)\s*\(",
                    lowered,
                )
            )

        def is_synthetic_parity_precheck(command: str) -> bool:
            lowered = command.lower()
            required = (
                "synthetic_coordinate_parity_ok",
                "assert",
                "even",
                "odd",
                "neighbor",
                "distance",
            )
            return all(marker in lowered for marker in required) and bool(
                re.search(r"\bpython(?:3)?\b", lowered)
            )

        first_inspection: tuple[int, int] | None = None
        first_precheck: tuple[int, int] | None = None
        persisted_test = False
        for episode, command_index, command in command_stream:
            position = (episode, command_index)
            if first_inspection is None and is_current_artifact_inspection(command):
                first_inspection = position
            if first_precheck is None and is_synthetic_parity_precheck(command):
                first_precheck = position
            lowered = command.lower()
            if (
                "def test_synthetic_coordinate_parity" in lowered
                and "even" in lowered
                and "odd" in lowered
                and "neighbor" in lowered
                and "distance" in lowered
            ):
                persisted_test = True

        marker_output_seen = False
        for prompt_path in verifier_logs.glob("episode-*/prompt.txt"):
            try:
                prompt = prompt_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "SYNTHETIC_COORDINATE_PARITY_OK" in prompt:
                marker_output_seen = True
                break

        violations: list[str] = []
        if first_precheck is None:
            violations.append(
                "missing synthetic even/odd neighbor-and-distance parity precheck"
            )
        elif first_inspection is not None and first_precheck >= first_inspection:
            violations.append(
                "synthetic coordinate parity precheck did not precede current artifact inspection"
            )
        if not marker_output_seen:
            violations.append("synthetic coordinate parity precheck did not execute successfully")
        if not persisted_test:
            violations.append(
                "generated verifier omitted test_synthetic_coordinate_parity"
            )
        return violations

    async def _build_previous_verifier_context(
        self,
        environment: BaseEnvironment,
        *,
        adversarial_recheck: bool = False,
    ) -> str:
        """Read the existing verifier script and build inheritance context for the prompt."""
        begin_marker = "__SKILL_VERIFIER_BEGIN__"
        end_marker = "__SKILL_VERIFIER_END__"
        try:
            result = await environment.exec(
                command=(
                    f"printf '{begin_marker}\\n'; "
                    "cat /root/verifier/test_outputs.py 2>/dev/null || true; "
                    f"printf '\\n{end_marker}\\n'"
                ),
                timeout_sec=10,
            )
            raw_output = result.stdout if result.stdout else ""
            if begin_marker in raw_output and end_marker in raw_output:
                script_content = raw_output.split(begin_marker, 1)[1].split(
                    end_marker, 1
                )[0].strip()
            else:
                # Backward-compatible fallback for test doubles and unusual shells.
                script_content = "\n".join(
                    line
                    for line in raw_output.splitlines()
                    if not line.startswith("bash: cannot set terminal process group")
                    and not line.startswith("bash: no job control in this shell")
                ).strip()
        except Exception:
            script_content = ""

        if not script_content:
            return "No previous verifier script exists. Write a new verifier from scratch following the workflow below."

        test_count = len(re.findall(r"def test_", script_content))
        logger.info(
            "Previous verifier script found with %d tests (generation #%d)",
            test_count,
            self._generation_count,
        )

        # Build failure info from last run's results
        failure_info = ""
        if self._last_result and self._last_result.test_details:
            failed = [d for d in self._last_result.test_details if d.get("status") == "FAILED"]
            if failed:
                failure_names = [d["name"] for d in failed[:20]]
                failure_info = (
                    f"\nThe previous run had {len(failed)} FAILING tests (out of {self._last_result.total_tests}):\n"
                    + "\n".join(f"  - {name}" for name in failure_names)
                    + (f"\n  (+ {len(failed) - 20} more...)" if len(failed) > 20 else "")
                    + "\n\nThese failures may be bugs in the TEST SCRIPT itself (not the output). "
                    "Read the script, diagnose each failure, and fix the test logic.\n"
                )

        rejection_context = (
            "A separate hidden evaluation rejected the candidate after the previous "
            "surrogate passed. You are NOT given hidden tests, expected answers, failure "
            "details, or evaluator artifacts. Do not look for them. Treat the rejection "
            "only as evidence that the public task instruction, input data, output "
            "semantics, runtime behavior, or edge cases were not covered deeply enough. "
            "Optional domain references may be consulted for general public knowledge, "
            "not as current-instance evidence.\n\n"
            if adversarial_recheck
            else
            "Improve the inherited verifier using the public task instruction, input "
            "data, runtime behavior, and output files. Optional domain references may "
            "be consulted for general public knowledge.\n\n"
        )

        provenance_context = (
            "SOURCE PROVENANCE: Keep task-instruction text, background document text, current "
            "input/output artifacts, and terminal/log output separate. Do not claim "
            "that any value or rule came from a background document unless you identify the exact "
            "file below /app/environment/doc/ and locate the supporting text in that "
            "file. Adjacent output from a later command is not background document content. If "
            "the source cannot be established, label it unknown rather than using the "
            "attribution to accept or reject the candidate.\n\n"
        )

        return (
            f"PREVIOUS VERIFIER EXISTS with {test_count} test(s) at /root/verifier/test_outputs.py.\n"
            f"{rejection_context}"
            f"{provenance_context}"
            "The previous verifier may have missed public requirements, semantic edge cases, "
            "or bugs in its own tests.\n\n"
            "QUALITY OVER QUANTITY — 30 correct tests are better than 200 buggy tests.\n"
            f"{failure_info}\n"
            "=== PREVIOUS SCRIPT CONTENT ===\n"
            f"```python\n{script_content}\n```\n"
            "=== END PREVIOUS SCRIPT ===\n\n"
            "You MUST:\n"
            "1. Review the previous script above (already in context)\n"
            "2. FIX BUGS in existing tests first — tests that raise AttributeError, KeyError,\n"
            "   SyntaxError, or other exceptions are BROKEN TEST CODE and must be fixed\n"
            "3. Remove or merge redundant/duplicate tests\n"
            "4. Only AFTER fixing existing tests, add new deeper tests for CONTENT CORRECTNESS:\n"
            "   - Independently derive expected values from environment data\n"
            "   - Test individual output items/entries separately (not all-at-once)\n"
            "   - Verify domain logic, not just structure/format\n"
            f"5. Keep total test count UNDER 60 — previous had {test_count}. "
            "Do NOT blindly add parameterized tests that multiply test count.\n"
            "6. The previous script already handles file existence and format — "
            "your new tests should focus on whether output VALUES are actually correct."
        )

    async def diagnose_failures(
        self,
        environment: BaseEnvironment,
        instruction: str,
        logs_dir: Path,
        verification: VerificationResult,
    ) -> str:
        """Run a lightweight diagnosis agent to analyze failures without regenerating tests.

        Uses ``diagnosis_only.txt`` — a stripped-down prompt with only JSON
        format, file-writing instructions, and V8 diagnosis format (no V1-V7
        test-generation workflow).  The agent runs the existing locked test
        script, reads output files, and writes ``/root/verifier/diagnosis.md``.
        The test script is backed up before the run and restored afterward to
        preserve locking.

        Returns the diagnosis text (empty string on failure).
        """
        from libs.terminus_agent.agents.terminus_2.harbor_terminus_2_skills import (
            HarborTerminus2WithSkills,
        )

        # Backup the locked test script
        await environment.exec(
            command="cp /root/verifier/test_outputs.py /root/verifier/test_outputs.py.locked 2>/dev/null || true",
            timeout_sec=10,
        )

        # Delete previous diagnosis so we get a fresh one
        await environment.exec(
            command="rm -f /root/verifier/diagnosis.md /root/verifier_progress.md",
            timeout_sec=10,
        )

        # Build diagnosis context with failed test details
        failed_details = []
        for d in verification.test_details:
            if d.get("status") == "FAILED":
                msg = d.get("message", "")
                name = d.get("name", "unknown")
                failed_details.append(f"  - {name}: {msg}" if msg else f"  - {name}")

        diagnosis_context = (
            f"Current test results: {verification.tests_passed}/{verification.total_tests} passed.\nFailed tests:\n" + "\n".join(failed_details)
        )

        diag_logs = logs_dir / f"diagnosis-{self._generation_count}"
        diag_logs.mkdir(parents=True, exist_ok=True)

        prompt_template_path = Path(__file__).parent / "prompt_templates" / "diagnosis_only.txt"
        raw_template = prompt_template_path.read_text(encoding="utf-8")

        verifier_agent = HarborTerminus2WithSkills(
            logs_dir=diag_logs,
            model_name=self._model_name,
            temperature=self._temperature,
            prompt_template=str(prompt_template_path),
            max_episodes=8,
        )
        await verifier_agent._ensure_python3_installed(environment)
        verifier_agent._skill_loader = SkillDocLoader(environment=environment)
        # Escape braces in diagnosis_context so they survive str.format() in run()
        safe_diag_context = diagnosis_context.replace("{", "{{").replace("}", "}}")
        verifier_agent._prompt_template = raw_template.replace("{diagnosis_context}", safe_diag_context)

        logger.info("Starting diagnosis-only verifier agent (model=%s)", self._model_name)

        try:
            await asyncio.wait_for(
                verifier_agent.run(instruction, environment, AgentContext()),
                timeout=self._diagnosis_timeout_sec,
            )
        except TimeoutError:
            logger.warning(
                "Diagnosis agent timed out after %ss",
                self._diagnosis_timeout_sec,
            )
        except Exception as exc:
            logger.warning("Diagnosis agent failed: %s", exc)

        # Read the diagnosis
        diagnosis = await self._read_diagnosis(environment)

        # Restore the locked test script
        await environment.exec(
            command="cp /root/verifier/test_outputs.py.locked /root/verifier/test_outputs.py 2>/dev/null || true",
            timeout_sec=10,
        )

        logger.info("Diagnosis-only agent completed (%d chars)", len(diagnosis))
        return diagnosis

    async def _read_diagnosis(self, environment: BaseEnvironment) -> str:
        """Read /root/verifier/diagnosis.md from the container."""
        try:
            result = await environment.exec(
                command="cat /root/verifier/diagnosis.md 2>/dev/null",
                timeout_sec=10,
            )
            raw = (result.stdout or "").strip()
            if not raw:
                return ""
            # Filter out shell warnings (e.g. "bash: cannot set terminal process group")
            from libs.terminus_agent.agents.terminus_2.skill_docs import is_shell_warning

            lines = [line for line in raw.splitlines() if not is_shell_warning(line)]
            return "\n".join(lines).strip()
        except Exception:
            return ""

    def reset(self) -> None:
        """Reset generation counter (call at the start of each evolution run)."""
        self._generation_count = 0
        self._last_result = None
