from __future__ import annotations

import asyncio
import ast
import inspect
import json
import types
import zipfile
from pathlib import Path

import pytest
from harbor.agents.installed.base import ExecInput

from libs.terminus_agent.agents.claude_code_skills import ClaudeCodeSkills
from libs.terminus_agent.agents.claude_code_vertex import (
    ClaudeCodeProviderError,
    configure_vertex_commands,
    validate_vertex_transcript,
)
from libs.terminus_agent.agents.terminus_2.harbor_terminus_2_evolution import (
    HarborTerminus2Evolution,
)
from libs.terminus_agent.agents.terminus_2.harbor_terminus_2_skills import (
    Command,
    HarborTerminus2WithSkills,
)
from libs.terminus_agent.evolution.combinatorial_budget import (
    combinatorial_search_budget_issue,
    referenced_python_scripts,
)
from libs.terminus_agent.evolution.independent_verifier import IndependentVerifier
from libs.terminus_agent.evolution.models import VerificationResult
from libs.terminus_agent.evolution.report_generator import generate_evolution_report
from libs.terminus_agent.agents.terminus_2.terminus_json_plain_parser import (
    TerminusJSONPlainParser,
)
from libs.terminus_agent.llms.chat import Chat
from libs.terminus_agent.evolution import skill_information_boundary
from libs.terminus_agent.evolution.skill_information_boundary import (
    audit_evolved_skill_directory,
)


class _Result:
    def __init__(self, stdout: str = "", return_code: int = 0):
        self.stdout = stdout
        self.return_code = return_code


def _write_range_fixture_xlsx(path: Path) -> None:
    """Write a tiny OOXML workbook without optional spreadsheet packages."""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Gold price" sheetId="1" r:id="rId1"/><sheet name="Value" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>"""
    prices = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
  <row r="1"><c r="A1" t="inlineStr"><is><t>Date</t></is></c><c r="B1" t="inlineStr"><is><t>Price</t></is></c></row>
  <row r="2"><c r="A2" t="inlineStr"><is><t>1990M1</t></is></c><c r="B2"><v>400</v></c></row>
  <row r="3"><c r="A3" t="inlineStr"><is><t>2025M9</t></is></c><c r="B3"><v>3600</v></c></row>
</sheetData></worksheet>"""
    table = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
  <row r="1"><c r="A1" t="inlineStr"><is><t>metadata</t></is></c><c r="C1" t="inlineStr"><is><t>Entity A</t></is></c><c r="D1" t="inlineStr"><is><t>Entity B</t></is></c><c r="E1" t="inlineStr"><is><t>Entity C</t></is></c></row>
  <row r="18"><c r="A18"><v>2025</v></c></row>
</sheetData></worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", prices)
        archive.writestr("xl/worksheets/sheet2.xml", table)


class _Environment:
    def __init__(self, responses: list[_Result]):
        self._responses = iter(responses)

    async def exec(self, **_kwargs):
        return next(self._responses)


def test_evolution_defaults_to_fresh_agent_skill_only_oracle(tmp_path: Path) -> None:
    agent = HarborTerminus2Evolution(
        logs_dir=tmp_path,
        model_name="test/model",
    )
    assert agent._gt_oracle_agent == "claude-code-skill-only"


_UNBOUNDED_MAP_SEARCH = """
from itertools import combinations, product
best = None
for city_center in land_tiles:
    for districts in combinations(specialty_options, 3):
        for placement in product(*candidate_positions):
            evaluate(city_center, districts, placement)
"""


def test_combinatorial_budget_gate_rejects_full_domain_cartesian_search() -> None:
    issue = combinatorial_search_budget_issue(_UNBOUNDED_MAP_SEARCH)
    assert issue is not None
    assert "product" in issue
    assert "global" in issue


def test_combinatorial_budget_gate_rejects_per_product_limit() -> None:
    source = """
from itertools import combinations, product
for city_center in land_tiles:
    for districts in combinations(specialty_options, 3):
        total_combos = 1
        for choices in candidate_positions:
            total_combos *= len(choices)
        if total_combos > 50000:
            continue
        for placement in product(*candidate_positions):
            evaluate(city_center, districts, placement)
"""
    issue = combinatorial_search_budget_issue(source)
    assert issue is not None
    assert "global" in issue


def test_combinatorial_budget_gate_allows_fail_closed_global_budget() -> None:
    source = """
from itertools import combinations, product
def search(land_tiles, specialty_options, candidate_positions, max_evaluations):
    evaluated = 0
    best = None
    for city_center in land_tiles:
        for districts in combinations(specialty_options, 3):
            for placement in product(*candidate_positions):
                if evaluated >= max_evaluations:
                    return best
                evaluated += 1
                best = evaluate(city_center, districts, placement)
    return best
"""
    assert combinatorial_search_budget_issue(source) is None


def test_combinatorial_budget_gate_allows_bounded_beam_and_local_search() -> None:
    source = """
def search(initial_state, max_iterations=20, beam_width=32):
    beam = [initial_state]
    for _ in range(max_iterations):
        candidates = []
        for state in beam:
            candidates.extend(local_neighbors(state))
        beam = sorted(candidates, key=score, reverse=True)[:beam_width]
    return beam[0]
"""
    assert combinatorial_search_budget_issue(source) is None


def test_combinatorial_budget_gate_allows_small_fixed_combinations() -> None:
    source = """
from itertools import combinations
for trio in combinations(range(6), 3):
    verify_synthetic_case(trio)
"""
    assert combinatorial_search_budget_issue(source) is None


def test_combinatorial_budget_gate_rejects_full_domain_bitmask_powerset() -> None:
    source = """
for tile in land_tiles:
    for mask in range(1 << len(candidate_positions)):
        evaluate_subset(tile, mask)
"""
    issue = combinatorial_search_budget_issue(source)
    assert issue is not None
    assert "powerset" in issue


def test_evolution_execute_gate_treats_inline_search_as_advisory(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    command = Command(
        keystrokes="python3 << 'PY'\n" + _UNBOUNDED_MAP_SEARCH + "PY\n",
        duration_sec=60,
    )

    class _ExecEnvironment:
        environment_dir = tmp_path / "environment"

        def __init__(self) -> None:
            self.commands: list[str] = []
            self.environment_dir.mkdir()

        async def exec(self, **kwargs):
            self.commands.append(kwargs["command"])
            return type("Result", (), {"stdout": "search completed", "stderr": ""})()

    agent = object.__new__(HarborTerminus2Evolution)
    agent._timeout_multiplier = 1.0
    environment = _ExecEnvironment()
    output = asyncio.run(agent._execute_commands(environment, [command]))

    assert environment.commands == [command.keystrokes]
    assert "search completed" in output
    assert "search-budget advisory" in caplog.text


@pytest.mark.parametrize(
    "command",
    [
        "ls /root/verifier && cat /root/verifier/test_outputs.py",
        "python3 -m pytest /tests/test.sh",
        "find / -name test_outputs.py -print",
        "cat /app/verifier/reference_solution.json",
        "cp /root/ground_truth/output.csv /tmp/result.csv",
    ],
)
def test_evolution_evaluator_boundary_rejects_protected_artifacts(
    command: str,
) -> None:
    assert HarborTerminus2Evolution._hidden_evaluator_access_issue(command)


def test_evolution_execute_gate_rejects_evaluator_access_without_running_it() -> None:
    command = Command(
        keystrokes="ls /root/verifier/ && cat /root/verifier/*.py\n",
        duration_sec=1,
    )

    class _NoExecEnvironment:
        async def exec(self, **_kwargs):
            raise AssertionError("protected evaluator command must not execute")

    agent = object.__new__(HarborTerminus2Evolution)
    output = asyncio.run(agent._execute_commands(_NoExecEnvironment(), [command]))

    assert "COMMAND REJECTED BY EVALUATOR INFORMATION-BOUNDARY GATE" in output
    assert "ordinary runtime diagnostics" in output


def test_evolution_execute_gate_rejects_repository_history_without_running_it() -> None:
    command = Command(
        keystrokes="git log --oneline -5 && git show HEAD~1:src/App.java\n",
        duration_sec=1,
    )

    class _NoExecEnvironment:
        async def exec(self, **_kwargs):
            raise AssertionError("repository-history command must not execute")

    agent = object.__new__(HarborTerminus2Evolution)
    agent._instruction = "Diagnose and repair the current source checkout."
    output = asyncio.run(agent._execute_commands(_NoExecEnvironment(), [command]))

    assert "COMMAND REJECTED BY REPOSITORY-HISTORY" in output
    assert "current checkout" in output


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest /app/tests/unit/test_public_api.py -q",
        "npm test",
        "cat /app/environment/doc/verification-background.md",
    ],
)
def test_evolution_evaluator_boundary_allows_public_project_validation(
    command: str,
) -> None:
    assert HarborTerminus2Evolution._hidden_evaluator_access_issue(command) is None


def test_combinatorial_budget_gate_finds_direct_python_script_paths() -> None:
    assert referenced_python_scripts(
        "python3 -u /root/search.py --scenario /data/scenario.json"
    ) == ("/root/search.py",)


def test_evolved_skill_gate_requires_evo_prefix() -> None:
    agent = object.__new__(HarborTerminus2Evolution)
    no_evo = _Environment([_Result("/app/environment/skills/spring-migration/SKILL.md\n")])
    assert asyncio.run(agent._find_evolved_skill_manifests(no_evo)) == []

    with_evo = _Environment(
        [_Result("/app/environment/skills/evo-spring-migration/SKILL.md\n")]
    )
    assert asyncio.run(agent._find_evolved_skill_manifests(with_evo)) == [
        "/app/environment/skills/evo-spring-migration/SKILL.md"
    ]


def test_continuation_selects_preexisting_skills_for_oracle_and_persistence() -> None:
    names = {"skill-creator", "helper", "evo-existing", "evo-new"}
    assert HarborTerminus2Evolution._select_evolved_skill_names(names) == [
        "evo-existing",
        "evo-new",
    ]

    oracle_source = inspect.getsource(
        HarborTerminus2Evolution._export_evolved_skills_to_host
    )
    persistence_source = inspect.getsource(
        HarborTerminus2Evolution._import_agent_created_skills
    )
    assert "_select_evolved_skill_names" in oracle_source
    assert "_select_evolved_skill_names" in persistence_source
    assert "current_skills - self._pre_existing_skills" not in oracle_source
    assert "current_skills - pre_existing_skills" not in persistence_source


def test_setup_restores_persisted_skills_before_run_refresh() -> None:
    setup_source = inspect.getsource(HarborTerminus2Evolution.setup)
    assert "_inject_host_evolved_skills" in setup_source
    assert setup_source.index("_inject_host_evolved_skills") < setup_source.index(
        "_inject_previous_verifier"
    )


def test_fresh_source_knowledge_eligibility_requires_empty_evolution_lineage() -> None:
    eligible = HarborTerminus2Evolution._fresh_run_source_knowledge_eligibility
    assert eligible({"skill-creator", "public-helper"}, [])
    assert not eligible({"skill-creator", "evo-seeded"}, [])
    assert not eligible({"skill-creator"}, ["evo-restored"])


def test_final_gt_paths_audit_information_boundary_but_do_not_gate_oracle() -> None:
    exit_source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    max_boundary = exit_source.index('stage="max_interventions_final"')
    max_oracle = exit_source.index('f"gt-oracle-max-')
    assert max_boundary < max_oracle
    max_tail = exit_source[max_boundary:max_oracle]
    assert "is advisory" in max_tail
    assert "information_boundary_gate" not in max_tail

    run_source = inspect.getsource(HarborTerminus2Evolution.run)
    final_boundary = run_source.index('stage="post_execution_final"')
    final_oracle = run_source.index('oracle_label="gt-oracle-final"')
    assert final_boundary < final_oracle
    final_tail = run_source[final_boundary:final_oracle]
    assert "is advisory" in final_tail
    assert "final_oracle_boundary_blocked" not in run_source
    assert "information_boundary_gate" not in final_tail


def test_evolved_skill_gate_runs_before_surrogate_generation() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    gate = source.index("_evolved_skill_schema_preflight")
    surrogate = source.index("Running surrogate verifier")
    assert gate < surrogate


def test_skill_schema_gate_runs_before_caps_surrogate_and_gt() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    gate = source.index("_evolved_skill_schema_preflight")
    cap = source.index("cap_hit =")
    surrogate = source.index('f"[evolution] Running surrogate verifier')
    gt = source.index('f"[evolution] Running GT oracle')
    assert gate < cap < surrogate < gt
    assert '"pre_gt" if self._skip_surrogate_verifier' in source


def test_skill_schema_feedback_exposes_exact_safe_errors() -> None:
    issue = (
        "/app/environment/skills/evo-example/SKILL.md: "
        "`description` must be a non-empty string [empty_description]"
    )
    feedback = HarborTerminus2Evolution._build_skill_schema_feedback([issue])
    assert "Exact schema errors" in feedback
    assert issue in feedback
    assert "did not consume a GT iteration" in feedback
    assert "repair" in feedback


def test_framework_never_authors_fallback_skill_manifests() -> None:
    source = inspect.getsource(HarborTerminus2Evolution)
    assert "_ensure_evolved_skill_manifests" not in source
    assert "Created fallback SKILL.md" not in source


def test_oracle_skill_digest_parser_ignores_shell_noise() -> None:
    digest = "a" * 64
    environment = _Environment(
        [
            _Result(
                "bash: no job control in this shell\n"
                + digest
                + "  -\n"
            )
        ]
    )
    assert asyncio.run(
        HarborTerminus2Evolution._container_evolved_skill_digest(environment)
    ) == digest


def test_gt_oracle_forwards_declared_verifier_environment(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    environment_dir = task_dir / "environment"
    tests_dir = task_dir / "tests"
    environment_dir.mkdir(parents=True)
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    (task_dir / "task.toml").write_text(
        'version = "1.1"\n\n[verifier.env]\nREPO_ID = "example/repo"\n',
        encoding="utf-8",
    )

    class _OracleEnvironment:
        def __init__(self) -> None:
            self.environment_dir = environment_dir
            self.calls: list[dict] = []
            self.responses = iter(
                [
                    _Result("missing\n"),
                    _Result(),
                    _Result(),
                    _Result("1 passed in 0.01s\n"),
                    _Result(),
                ]
            )

        async def upload_dir(self, **_kwargs) -> None:
            return None

        async def exec(self, **kwargs):
            self.calls.append(kwargs)
            return next(self.responses)

    environment = _OracleEnvironment()
    agent = object.__new__(HarborTerminus2Evolution)
    result = asyncio.run(agent._run_ground_truth_evaluation(environment))

    test_call = next(
        call for call in environment.calls if call["command"] == "bash /tests/test.sh 2>&1"
    )
    assert test_call["env"] == {"REPO_ID": "example/repo"}
    assert result is not None
    assert result["tests_passed"] == 1
    assert result["total_tests"] == 1


def test_gt_evaluation_always_reads_fractional_canonical_reward(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    environment_dir = task_dir / "environment"
    tests_dir = task_dir / "tests"
    environment_dir.mkdir(parents=True)
    tests_dir.mkdir()
    (tests_dir / "test.sh").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")

    class _OracleEnvironment:
        def __init__(self) -> None:
            self.environment_dir = environment_dir
            self.responses = iter(
                [
                    _Result("missing\n"),
                    _Result(),
                    _Result(),
                    _Result("10 passed in 0.01s\n"),
                    _Result("0.850\n"),
                ]
            )

        async def upload_dir(self, **_kwargs) -> None:
            return None

        async def exec(self, **_kwargs):
            return next(self.responses)

    agent = object.__new__(HarborTerminus2Evolution)
    result = asyncio.run(agent._run_ground_truth_evaluation(_OracleEnvironment()))

    assert result is not None
    assert result["tests_passed"] == 10
    assert result["total_tests"] == 10
    assert result["reward"] == pytest.approx(0.85)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"tests_passed": 10, "total_tests": 10, "reward": 0.85}, (False, 0.85)),
        ({"tests_passed": 10, "total_tests": 10, "reward": 1.0}, (True, 1.0)),
        ({"tests_passed": 10, "total_tests": 10}, (True, 1.0)),
        ({"tests_passed": 10, "total_tests": 10, "reward": "bad"}, (True, 1.0)),
        ({"tests_passed": 0, "total_tests": 0, "reward": 1.0}, (True, 1.0)),
    ],
)
def test_gt_full_score_uses_canonical_reward_then_safe_fallback(
    result: dict,
    expected: tuple[bool, float],
) -> None:
    assert HarborTerminus2Evolution._gt_full_score_and_reward(result) == expected


def test_best_gt_snapshot_ranks_and_replays_canonical_reward(
    tmp_path: Path,
) -> None:
    agent = object.__new__(HarborTerminus2Evolution)
    agent._best_gt_snapshot = None
    agent._intervention_history = []
    exported = iter([tmp_path / "snapshot-a", tmp_path / "snapshot-b"])

    async def export_snapshot(_self, _environment):
        path = next(exported)
        path.mkdir()
        return path

    agent._export_evolved_skills_to_host = types.MethodType(export_snapshot, agent)

    fractional = {
        "passed": False,
        "tests_passed": 10,
        "total_tests": 10,
        "pass_rate": 1.0,
        "reward": 0.8,
    }
    asyncio.run(agent._maybe_save_best_snapshot(object(), fractional, 1))
    assert agent._best_gt_snapshot["passed"] is False
    assert agent._best_gt_snapshot["reward"] == pytest.approx(0.8)

    # Canonical reward, not structural pytest pass rate, defines the better round.
    better_reward = {
        "passed": False,
        "tests_passed": 5,
        "total_tests": 10,
        "pass_rate": 0.5,
        "reward": 0.9,
    }
    asyncio.run(agent._maybe_save_best_snapshot(object(), better_reward, 2))
    assert agent._best_gt_snapshot["reward"] == pytest.approx(0.9)
    assert agent._best_gt_snapshot["pass_rate"] == pytest.approx(0.5)

    agent._intervention_history = [{"gt_result": better_reward}]
    replay = agent._recorded_best_gt_result()
    assert replay is not None
    assert replay["passed"] is False
    assert replay["reward"] == pytest.approx(0.9)
    assert replay["pass_rate"] == pytest.approx(0.5)


def test_intervention_history_preserves_canonical_reward() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    assert source.count('"reward": gt_oracle_result.get("reward")') >= 2


def test_evolution_report_displays_reward_separately_from_test_pass_rate() -> None:
    report = generate_evolution_report(
        {
            "task_name": "fractional-example",
            "gt_oracle_result": {"passed": False, "reward": 0.8},
            "intervention_history": [
                {
                    "intervention_number": 1,
                    "trigger": "surrogate_pass",
                    "surrogate_result": None,
                    "gt_result": {
                        "tests_passed": 10,
                        "total_tests": 10,
                        "pass_rate": 1.0,
                        "reward": 0.8,
                    },
                }
            ],
        }
    )

    assert "Canonical reward | 0.8" in report
    assert "10/10 (100% tests), reward=0.8" in report


def test_gt_feedback_categories_are_broad_and_omit_hidden_details() -> None:
    gt_result = {
        "test_details": [
            {
                "name": "test_segment_recall_expected_boundary_236_0",
                "status": "FAILED",
                "message": "expected 236.0 but got 52.0",
            },
            {
                "name": "test_audio_json_waveform_correspondence",
                "status": "FAILED",
                "message": "correlation 0.1115 below hidden threshold",
            },
            {"name": "test_report_schema", "status": "PASSED"},
        ]
    }

    categories = HarborTerminus2Evolution._safe_gt_failure_categories(gt_result)

    assert categories == [
        "semantic selection and coverage",
        "temporal or media consistency",
    ]
    rendered = " ".join(categories)
    assert "236" not in rendered
    assert "52" not in rendered
    assert "0.1115" not in rendered
    assert "expected" not in rendered


def test_gt_feedback_can_name_public_output_field_without_leaking_values() -> None:
    instruction = '''Write /root/answers.json using {"q1_answer": 0, "q2_answer": 0}.'''
    gt_result = {
        "raw_output": '''
        assert answers["q1_answer"] > 0
>       assert answers["q2_answer"] == ground_truth["q2_answer"]
E       assert 3457 == 2451
hidden row identifier: manager_0001037389
''',
    }

    fields = HarborTerminus2Evolution._safe_gt_failed_output_fields(
        gt_result,
        instruction,
    )

    assert fields == ["q2_answer"]
    rendered = " ".join(fields)
    assert "3457" not in rendered
    assert "2451" not in rendered
    assert "0001037389" not in rendered


def test_gt_feedback_rejects_evaluator_only_field_name() -> None:
    fields = HarborTerminus2Evolution._safe_gt_failed_output_fields(
        {
            "raw_output": (
                '> assert output["hidden_current_row_004"] == 0\n'
                '> assert answers["q2_answer"] == 1'
            )
        },
        'Public schema: {"q2_answer": 0}',
    )

    assert fields == ["q2_answer"]


def test_gt_attribution_feedback_requires_helper_only_transfer_without_details() -> None:
    gt_result = {
        "failure_reasons": [
            "Clean evaluation bypassed the immutable evolved Skill",
        ],
        "raw_output": (
            "fresh agent used Edit on /current/private/path.py with hidden_value_42"
        ),
    }

    guidance = HarborTerminus2Evolution._safe_gt_refinement_guidance(gt_result)

    assert len(guidance) == 1
    rendered = guidance[0]
    assert "manual artifact or source mutation" in rendered
    assert "end-to-end helper" in rendered
    assert "/current/private/path.py" not in rendered
    assert "hidden_value_42" not in rendered


def test_surrogate_feedback_redacts_mario_instance_diagnosis_replay() -> None:
    """Regression: the contaminated Mario episode-98 diagnosis stays host-only."""
    diagnosis = """# Diagnosis of Failed Tests

## test_coins_frame_004_color_verification
- **Actual**: CSV reports coins=4 for frame 004
- **Expected**: coins=0. The detections at scores 0.78-0.80 are question mark blocks.
- **Root cause**: Patches have BGR [74, 109, 134] and distance 59.9.
- **Fix suggestion**: Increase the threshold to at least 0.85.

## test_coins_frame_007_color_verification
- **Actual**: CSV reports coins=1 for frame 007
- **Expected**: coins=0; color distance is 63.5.
"""
    verification = VerificationResult(
        source="script",
        total_tests=62,
        tests_passed=60,
        tests_failed=2,
        test_details=[
            {
                "name": "test_coins_frame_004_color_verification",
                "status": "FAILED",
                "message": "expected 0, got 4 at frame 004; threshold 0.85",
            },
            {
                "name": "test_coins_frame_007_color_verification",
                "status": "FAILED",
                "message": "expected 0, got 1 at frame 007; BGR [79, 110, 136]",
            },
        ],
        raw_output="GROUND_TRUTH coins=[0, 2, 0, 0, 4, 1, 0, 0]",
        diagnosis=diagnosis,
    )

    feedback = HarborTerminus2Evolution._build_surrogate_feedback(verification)

    assert "Broad failure dimensions observed: semantic selection and coverage." in feedback
    for leaked in (
        "60/62",
        "test_coins_frame_004_color_verification",
        "test_coins_frame_007_color_verification",
        "frame 004",
        "frame 007",
        "Actual",
        "Expected",
        "0.78",
        "0.80",
        "0.85",
        "BGR",
        "59.9",
        "63.5",
        "GROUND_TRUTH",
        "[0, 2, 0, 0, 4, 1, 0, 0]",
    ):
        assert leaked not in feedback


@pytest.mark.parametrize(
    ("replay_name", "host_only_issues", "leaked_tokens"),
    [
        (
            "lab-unit-harmonization episode-40",
            [
                "evo-lab-harmonizer/SKILL.md:58 [current_input_literal_cluster] "
                "embeds current labels 'Phosphorus', 'Total Protein', 'Prealbumin'",
                "evo-lab-harmonizer/SKILL.md:70 [current_input_value] matches "
                "environment/data/ckd_lab_data.csv: 0.077",
                "evo-lab-harmonizer/SKILL.md:71 [undeclared_spreadsheet_layout_literal] "
                "embeds spreadsheet address/range 'T3'",
            ],
            ("evo-lab-harmonizer", "Phosphorus", "Prealbumin", "0.077", "T3"),
        ),
        (
            "video-silence-remover episode-22",
            [
                "evo-video-silence-remover/scripts/audio_analysis.py:167 "
                "[unjustified_fixed_threshold] energy_threshold=0.5",
                "evo-video-silence-remover/scripts/audio_analysis.py:132 "
                "[unjustified_decision_cutoff] unstated cutoff 0.4",
                "evo-video-silence-remover/scripts/video_editor.py:182 "
                "[unjustified_decision_cutoff] unstated cutoff 0.01",
            ],
            ("audio_analysis.py", "video_editor.py", ":167", "0.5", "0.4", "0.01"),
        ),
        (
            "paper-anonymizer episode-37",
            [
                "evo-pdf-anonymizer/SKILL.md:72 "
                "[undeclared_current_artifact_manifest_literal] /root/paper1.pdf",
                "evo-pdf-anonymizer/scripts/anonymize.py:167 "
                "[current_artifact_path_literal] paper2.pdf",
                "evo-pdf-anonymizer/scripts/anonymize.py:200 "
                "[current_artifact_path_literal] paper3.pdf",
            ],
            ("evo-pdf-anonymizer", "anonymize.py", ":167", "paper1.pdf", "paper2.pdf", "paper3.pdf"),
        ),
    ],
)
def test_static_boundary_feedback_keeps_real_episode_findings_host_only(
    replay_name: str,
    host_only_issues: list[str],
    leaked_tokens: tuple[str, ...],
) -> None:
    """Replay the three live contaminations that motivated the transitive gate."""
    feedback = HarborTerminus2Evolution._build_static_gate_feedback(
        "information_boundary", host_only_issues
    )

    assert replay_name
    assert "SKILL INFORMATION-BOUNDARY FAILURE" in feedback
    assert "Issues:" not in feedback
    for leaked in leaked_tokens:
        assert leaked not in feedback


@pytest.mark.parametrize(
    "gate",
    [
        "missing_frontmatter",
        "transfer_api",
        "hard_property",
        "information_boundary",
        "spreadsheet_recalculation",
    ],
)
def test_every_static_gate_feedback_uses_fixed_answer_free_guidance(gate: str) -> None:
    issues = [
        "/root/current/private.xlsx:236 [schema_key] expected 0.85 for entity ABC-42"
    ]

    feedback = HarborTerminus2Evolution._build_static_gate_feedback(gate, issues)

    for leaked in (
        "/root/current/private.xlsx",
        ":236",
        "schema_key",
        "0.85",
        "ABC-42",
        "expected",
    ):
        assert leaked not in feedback


def test_transfer_api_advisory_runs_before_surrogate_generation() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    gate = source.index("trigger=skill_transfer_api")
    surrogate = source.index("Running surrogate verifier")
    assert gate < surrogate


def test_hard_property_evidence_advisory_runs_before_surrogate_generation() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    gate = source.index("trigger=hard_property_evidence_gate")
    surrogate = source.index("Running surrogate verifier")
    assert gate < surrogate


def test_spreadsheet_recalculation_advisory_runs_before_surrogate_generation() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    gate = source.index("trigger=spreadsheet_recalculation_gate")
    surrogate = source.index("Running surrogate verifier")
    assert gate < surrogate


def test_formula_free_spreadsheet_does_not_require_recalculation_engine() -> None:
    source = inspect.getsource(
        HarborTerminus2Evolution._spreadsheet_recalculation_issues
    )
    assert source.index("if formula_count == 0") < source.index(
        'office = shutil.which("libreoffice")'
    )
    assert 'name.startswith("xl/worksheets/")' in source


def test_spreadsheet_gate_checks_public_horizon_and_index_orientation() -> None:
    source = inspect.getsource(
        HarborTerminus2Evolution._spreadsheet_recalculation_issues
    )
    assert "near_term_exposure" in source
    assert "annualized_rows" in source
    assert "runtime-discovered labels" in source
    assert "horizontal_index_with_match_row" in source
    assert "MATCH to the column dimension" in source
    assert 'cached_cell.data_type == "e"' in source
    assert "instruction_encoded" in source
    assert "if issue not in errors" in source

    exit_source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    feedback_source = inspect.getsource(
        HarborTerminus2Evolution._build_static_gate_feedback
    )
    assert '"spreadsheet_recalculation"' in exit_source
    assert "strengthen " in feedback_source
    assert "row/column orientation" in feedback_source


def test_embedded_spreadsheet_gate_rejects_ambiguous_horizontal_index() -> None:
    method_source = inspect.getsource(
        HarborTerminus2Evolution._spreadsheet_recalculation_issues
    )
    method_tree = ast.parse(method_source.lstrip())
    checker_assignment = next(
        node
        for node in ast.walk(method_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "checker"
            for target in node.targets
        )
    )
    checker_source = ast.literal_eval(checker_assignment.value)
    compile(checker_source, "<embedded-spreadsheet-gate>", "exec")

    checker_tree = ast.parse(checker_source)
    regex_assignment = next(
        node
        for node in ast.walk(checker_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "horizontal_index_with_match_row"
            for target in node.targets
        )
    )
    regex_module = ast.Module(
        body=[ast.Import(names=[ast.alias("re")]), regex_assignment],
        type_ignores=[],
    )
    namespace: dict[str, object] = {}
    exec(
        compile(
            ast.fix_missing_locations(regex_module),
            "<embedded-index-orientation-regex>",
            "exec",
        ),
        namespace,
    )
    pattern = namespace["horizontal_index_with_match_row"]

    assert pattern.search(
        "=INDEX($C$12:$K$12,MATCH(D20,$C$11:$K$11,0))"
    )
    assert pattern.search(
        "=INDEX('Source'!$C$18:$P$18,MATCH(D20,'Source'!$C$1:$P$1,0))"
    )
    assert not pattern.search(
        "=INDEX($C$12:$K$12,1,MATCH(D20,$C$11:$K$11,0))"
    )


def test_declared_spreadsheet_output_parser_ignores_inputs() -> None:
    instruction = (
        "Read `/root/vendors.xlsx` and `/root/source.xlsx`.\n"
        "Save your result to `/root/output/result.xlsx`.\n"
        "Output answers in `second.xlsx`."
    )
    assert HarborTerminus2Evolution._declared_spreadsheet_outputs(instruction) == [
        "/root/output/result.xlsx",
        "/root/second.xlsx",
    ]


def test_active_evolution_has_room_to_create_a_skill_before_stale_check() -> None:
    assert HarborTerminus2Evolution._STALE_EPISODE_LIMIT >= 30


def test_default_episode_budget_allows_complex_skill_repair() -> None:
    parameters = inspect.signature(HarborTerminus2WithSkills.__init__).parameters
    assert parameters["max_episodes"].default >= 120
    assert parameters["max_output_tokens"].default >= 16384


def test_evolution_calls_model_with_explicit_output_budget() -> None:
    source = inspect.getsource(HarborTerminus2WithSkills.run)
    assert "max_tokens=self._max_output_tokens" in source


def test_json_prompts_forbid_simulated_multiple_turns() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompts = [
        repo_root
        / "libs/terminus_agent/agents/prompt-templates/terminus-evolution-json.txt",
        repo_root
        / "libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt",
    ]
    for prompt in prompts:
        text = prompt.read_text(encoding="utf-8")
        assert "Emit exactly ONE JSON object" in text
        assert "do not simulate terminal output or future turns" in text


def test_json_history_keeps_only_the_first_executable_turn() -> None:
    parser = TerminusJSONPlainParser()
    first = '{"analysis":"a","plan":"p","commands":[]}'
    second = '{"analysis":"fiction","plan":"future","commands":[]}'
    assert parser.executable_response(f"intro\n{first}\n{second}") == first


def test_chat_can_replace_fictional_tail_without_changing_usage() -> None:
    class _Model:
        def count_tokens(self, messages):
            return sum(len(str(item.get("content", ""))) for item in messages)

        def call(self, **_kwargs):
            return "full provider response"

    chat = Chat(_Model())
    chat.chat("prompt")
    original_output_tokens = chat.total_output_tokens
    chat.replace_last_assistant_response("executable response")
    assert chat.messages[-1]["content"] == "executable response"
    assert chat.total_output_tokens == original_output_tokens


def test_skill_audit_rejects_current_ids_but_allows_thresholds(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "records.csv").write_text(
        "record_id,description\nCASE_CURRENT_9087,current private record phrase\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "Always special-case CASE_CURRENT_9087.\n",
        encoding="utf-8",
    )
    (scripts / "utils.py").write_text(
        "def choose(value, score_threshold=83):\n    return value\n"
        "def segment(value, visual_diff_thresh=2.5):\n    return value\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(skill_root, task_dir, "Process records")
    kinds = {issue.kind for issue in issues}
    assert "current_input_value" in kinds
    assert "unjustified_fixed_threshold" not in kinds


def test_skill_audit_rejects_hard_property_prefix_from_negative_only_filter(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-lodging" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "render.py").write_text(
        "def render(records, pet_friendly):\n"
        "    eligible = [r for r in records if 'no pets' not in str(r.get('policy', '')).lower()]\n"
        "    if pet_friendly:\n"
        "        for record in eligible:\n"
        "            record['name'] = 'Pet-friendly ' + record['name']\n"
        "    return eligible\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select pet-friendly lodging and put each accommodation in a string field.",
    )

    matches = [
        issue
        for issue in issues
        if issue.kind == "hard_property_positive_evidence_missing"
    ]
    assert len(matches) == 1
    assert "same-entity" in matches[0].evidence
    assert "negative records" in matches[0].evidence


def test_skill_audit_rejects_missing_or_unrelated_policy_as_positive(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-lodging" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "render.py").write_text(
        "def render(record, pet_friendly):\n"
        "    policy = record.get('policy')\n"
        "    if pet_friendly and (policy is None or 'no pets' not in policy.lower()):\n"
        "        return 'Pet-friendly ' + record['name']\n"
        "    return record['name']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select pet-friendly lodging and put each accommodation in a string field.",
    )

    assert "hard_property_positive_evidence_missing" in {
        issue.kind for issue in issues
    }


def test_skill_audit_does_not_treat_request_flag_as_output_qualifier(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-lodging" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "request.py").write_text(
        "def parse(params):\n"
        "    pet_friendly = bool(params.get('pet_friendly'))\n"
        "    return {'pet_friendly': pet_friendly}\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select pet-friendly lodging and put each accommodation in a string field.",
    )

    assert "hard_property_positive_evidence_missing" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_same_entity_explicit_positive_property_evidence(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-lodging" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "render.py").write_text(
        "def classify_pet_policy(record):\n"
        "    raw_policy = record.get('policy')\n"
        "    if raw_policy is None:\n"
        "        return 'unknown'\n"
        "    normalized = str(raw_policy).lower()\n"
        "    if 'no pets' in normalized or 'pets prohibited' in normalized:\n"
        "        return 'negative'\n"
        "    if 'pets allowed' in normalized or 'pet-friendly' in normalized:\n"
        "        return 'positive'\n"
        "    return 'unknown'\n\n"
        "def render(record):\n"
        "    evidence_state = classify_pet_policy(record)\n"
        "    if evidence_state != 'positive':\n"
        "        raise ValueError('hard property is not positively supported')\n"
        "    return 'Pet-friendly — ' + record['name']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select pet-friendly lodging and put each accommodation in a string field.",
    )

    assert "hard_property_positive_evidence_missing" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_positive_evidence_from_a_different_entity(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-lodging" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "render.py").write_text(
        "def classify_pet_policy(policy_record):\n"
        "    raw_policy = policy_record.get('policy')\n"
        "    if raw_policy is None:\n"
        "        return 'unknown'\n"
        "    if 'no pets' in raw_policy.lower():\n"
        "        return 'negative'\n"
        "    if 'pets allowed' in raw_policy.lower():\n"
        "        return 'positive'\n"
        "    return 'unknown'\n\n"
        "def render(selected_record, unrelated_policy_record):\n"
        "    evidence_state = classify_pet_policy(unrelated_policy_record)\n"
        "    if evidence_state != 'positive':\n"
        "        raise ValueError('hard property is not positively supported')\n"
        "    return 'Pet-friendly — ' + selected_record['name']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select pet-friendly lodging and put each accommodation in a string field.",
    )

    assert "hard_property_positive_evidence_missing" in {
        issue.kind for issue in issues
    }


def test_cached_current_input_literals_preserve_overlap_results(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "records.csv").write_text(
        "record_id,category_path,description\n"
        "CASE_CURRENT_9087,Sports > Golf Equipment,unrelated prose\n"
        "CASE_OTHER_1042,Vehicles > Vehicle Parts,another unrelated row\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_file = skill_root / "evo-example" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    text = (
        "Always special-case CASE_CURRENT_9087 and combine Golf Equipment "
        "with Vehicle Parts.\n"
    )
    skill_file.write_text(text, encoding="utf-8")
    instruction = "Process the supplied records and category paths."

    uncached = skill_information_boundary._input_overlap_issues(
        skill_file,
        text,
        task_dir,
        instruction,
        skill_root,
    )
    literal_cache = skill_information_boundary._relevant_current_input_literals(
        task_dir,
        (text,),
    )
    cached = skill_information_boundary._input_overlap_issues(
        skill_file,
        text,
        task_dir,
        instruction,
        skill_root,
        literal_cache,
    )

    assert cached == uncached


def test_cached_current_input_prefilter_preserves_short_long_and_file_boundaries(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    data_file = data_dir / "records.csv"
    data_file.write_text(
        "id,value\n"
        "1,Golf\n"
        "2,CASE_CURRENT_VALUE_LONG_9087\n"
        "3,BOUNDARYBRIDGE\n",
        encoding="utf-8",
    )

    cache = skill_information_boundary._relevant_current_input_literals(
        task_dir,
        (
            "Use Golf and CASE_CURRENT_VALUE_LONG_9087; end with BOUNDARY",
            "BRIDGE starts this separate file.",
        ),
    )

    retained = {value for _kind, value in cache[data_file]}
    assert "Golf" in retained
    assert "CASE_CURRENT_VALUE_LONG_9087" in retained
    assert "BOUNDARYBRIDGE" not in retained


def test_skill_audit_reads_each_current_input_once_across_skill_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    data_file = data_dir / "records.csv"
    data_file.write_text(
        "record_id,description\nCASE_CURRENT_9087,current private record phrase\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (skill_root / "evo-example" / "SKILL.md").write_text(
        "Use CASE_CURRENT_9087 only as a current-record shortcut.\n",
        encoding="utf-8",
    )
    (scripts / "first.py").write_text(
        "TARGET = 'CASE_CURRENT_9087'\n",
        encoding="utf-8",
    )
    (scripts / "second.py").write_text(
        "def choose():\n    return 'CASE_CURRENT_9087'\n",
        encoding="utf-8",
    )
    original_iter = skill_information_boundary.iter_input_literals
    calls: list[Path] = []

    def counting_iter(path: Path):
        calls.append(path)
        yield from original_iter(path)

    monkeypatch.setattr(
        skill_information_boundary,
        "iter_input_literals",
        counting_iter,
    )

    issues = audit_evolved_skill_directory(skill_root, task_dir, "Process records")

    assert calls == [data_file]
    assert sum(issue.kind == "current_input_value" for issue in issues) == 3


def test_skill_audit_allows_numeric_thresholds_and_decision_cutoffs(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "camera.py").write_text(
        "roll_threshold = 2\n"
        "def tune(score_threshold=10):\n"
        "    return apply(cutoff=100) if roll_threshold > 2 else None\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive all camera thresholds from runtime evidence.",
    )
    kinds = {issue.kind for issue in issues}
    assert "unjustified_fixed_threshold" not in kinds
    assert "unjustified_decision_cutoff" not in kinds


def test_skill_audit_rejects_current_travel_request_serialized_into_skill(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    instruction = (
        'Build an itinerary: "We require a 7-day travel itinerary for two leaving '
        "from Minneapolis and covering three cities in Ohio, starting from March "
        "17th to March 23rd, 2022. Our budget is up to $5,100. Meals should include "
        'American, Mediterranean, Chinese, and Italian cuisines."\n'
        "Output each day as JSON with breakfast, lunch, and dinner fields."
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-travel" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "plan.py").write_text(
        "ORIGIN = 'Minneapolis'\n"
        "STATE = 'Ohio'\n"
        "START_DATE = 'March 17th'\n"
        "END_DATE = 'March 23rd'\n"
        "BUDGET = '$5,100'\n"
        "CUISINES = ['American', 'Mediterranean', 'Chinese', 'Italian']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(skill_root, task_dir, instruction)
    assert "current_instruction_instance_literal_cluster" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_instruction_format_and_standard_without_instance_values(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    instruction = (
        'Build an itinerary: "We require a 7-day trip from Minneapolis to Ohio in '
        'March 2022 with a $5,100 budget." Output JSON with a plan array.'
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-travel"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Read all current travel constraints from the instruction. Emit valid JSON "
        "with a plan array; validate its schema and date continuity.\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, instruction)
    assert "current_instruction_instance_literal_cluster" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_fixed_trip_shape_even_when_numbers_use_words(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    instruction = (
        'Plan travel: "Create a 7-day itinerary for two covering three cities. '
        'Select all other details from the current request."'
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-travel" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "shape.py").write_text(
        "TRIP_DAYS = 7\nCITY_COUNT = 3\nPARTY_SIZE = 2\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, instruction)
    assert "current_instruction_instance_literal_cluster" in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_cluster_of_current_taxonomy_labels(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "categories.csv").write_text(
        "category_path\n"
        "Sports > Golf Equipment\n"
        "Vehicles > Vehicle Parts\n"
        "Beauty > Hair Care\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Special-case Golf Equipment, Vehicle Parts, and Hair Care.\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Build a unified taxonomy from the supplied category paths.",
    )
    assert "current_input_literal_cluster" in {issue.kind for issue in issues}


def test_skill_audit_rejects_single_current_header_entity_special_case(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "reserves.csv").write_text(
        "description,value\n"
        "Czechia: Official Reserve Assets,12.5\n"
        "Georgia: Official Reserve Assets,9.0\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "normalize.py").write_text(
        "def normalize(country):\n"
        "    if country.startswith('Czechia'):\n"
        "        return 'Czechia'\n"
        "    return country\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Normalize supplied reserve entities from runtime metadata.",
    )
    assert "current_input_control_literal" in {issue.kind for issue in issues}


def test_skill_audit_allows_public_or_runtime_derived_entity_normalization(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "reserves.csv").write_text(
        "description,value\nCzechia: Official Reserve Assets,12.5\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "normalize.py").write_text(
        "def normalize(description, separator=':'):\n"
        "    return description.split(separator, 1)[0].strip()\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Normalize supplied reserve entities from runtime metadata.",
    )
    assert "current_input_control_literal" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_current_workbook_range_defaults(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    _write_range_fixture_xlsx(data_dir / "template.xlsx")

    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "parse.py").write_text(
        "def extract(start_year=1990, data_row=18, start_col=3):\n"
        "    return start_year, data_row, start_col\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Discover the workbook's ranges and years from its labels.",
    )
    range_issues = [
        issue for issue in issues if issue.kind == "current_input_range_default"
    ]
    assert len(range_issues) == 3


def test_skill_audit_allows_declared_or_runtime_workbook_ranges(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    _write_range_fixture_xlsx(data_dir / "template.xlsx")

    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "parse.py").write_text(
        "def declared(start_year=1990):\n"
        "    return start_year\n"
        "def derived(start_year=None):\n"
        "    return discover_year() if start_year is None else start_year\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Use the publicly declared 1990 start year; derive all other ranges.",
    )
    assert "current_input_range_default" not in {issue.kind for issue in issues}


def test_skill_audit_allows_unstated_decision_cutoffs(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "utils.py").write_text(
        "def classify(unique_ports, syn_ratio):\n"
        "    return unique_ports > 50 and syn_ratio > 0.5\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, "Classify traffic")
    assert "unjustified_decision_cutoff" not in {issue.kind for issue in issues}


def test_skill_audit_allows_fixed_model_selection_policy(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "pipeline.py").write_text(
        "fallback_n_clusters = 2\n"
        "def run(model, max_speakers=10):\n"
        "    return model.fit(n_clusters=2, target_top_clusters=14, noise_db=-23)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root, task_dir, "Select model settings from the supplied recording."
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_allows_fixed_tracking_geometry_and_lifetime_policy(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "tracker.py").write_text(
        "def track(max_distance=45, min_height=18, min_width=12, min_size=20, "
        "track_buffer=30, max_age=15, max_gap_seconds=2.5, min_frames=3, "
        "min_duration=4, pixel_radius=6):\n"
        "    return max_distance\n"
        "def accept(height, distance, gap, frame_window):\n"
        "    return height > 18 and distance < 45 and gap < 3 and frame_window > 8\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Track objects using settings derived from runtime geometry and timing.",
    )
    kinds = {issue.kind for issue in issues}
    assert "unjustified_fixed_policy" not in kinds
    assert "unjustified_decision_cutoff" not in kinds


def test_skill_audit_rejects_current_media_geometry_and_camera_calibration(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    environment = task_dir / "environment"
    environment.mkdir(parents=True)
    (environment / "input.mp4").write_bytes(b"current video")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-egomotion" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "estimate.py").write_text(
        "# Tuned against the current 1280x720 transform.\n"
        "roll_threshold = 2\n"
        "pan_scale = 0.35\n"
        "tilt_scale = 0.42\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Inspect the current video and derive camera motion at runtime.",
    )
    assert "current_artifact_geometry_calibration" in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_fixed_structured_map_runtime_policy(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "runtime-map.Civ6Map").write_bytes(b"runtime structured map")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-map-optimizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "optimizer.py").write_text(
        "WIDTH = 44\n"
        "HEIGHT = 26\n"
        "WRAP_X = True\n"
        "SPECIALTY_OPTIONS = ['CAMPUS', 'INDUSTRIAL_ZONE', 'COMMERCIAL_HUB']\n\n"
        "DEFAULT_SPEC_PRIORITY = ['CAMPUS', 'HARBOR', 'HOLY_SITE']\n"
        "STRATEGIC_RESOURCES = ['RESOURCE_IRON', 'RESOURCE_COAL', 'RESOURCE_OIL']\n\n"
        "def search(cc_scores):\n"
        "    selected = []\n"
        "    observed_layout = [(20, 15), (21, 14), (23, 13)]\n"
        "    for cx in range(18, 29):\n"
        "        selected.append((cx, observed_layout[0]))\n"
        "    selected.extend([center for score, center in cc_scores[:15]])\n"
        "    return selected\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read the supplied structured map and optimize a valid placement.",
    )
    kinds = {issue.kind for issue in issues}

    assert "fixed_structured_map_geometry" in kinds
    assert "fixed_runtime_rule_vocabulary" in kinds
    assert sum(issue.kind == "fixed_runtime_rule_vocabulary" for issue in issues) == 3
    assert "fixed_ranked_search_shortlist" in kinds
    assert "fixed_structured_map_search_window" in kinds
    assert "fixed_structured_map_coordinate_cluster" in kinds
    assert all("44" not in issue.evidence and "26" not in issue.evidence for issue in issues)


def test_skill_audit_allows_runtime_map_metadata_rules_and_budget(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "runtime-map.Civ6Map").write_bytes(b"runtime structured map")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-map-optimizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "optimizer.py").write_text(
        "def load_runtime_policy(connection, rule_source):\n"
        "    width, height, wrap_x = connection.execute('SELECT Width, Height, WrapX FROM Map').fetchone()\n"
        "    specialty_options = rule_source.permitted_categories()\n"
        "    return width, height, wrap_x, specialty_options\n\n"
        "def search(ranked_states, max_evaluations):\n"
        "    selected = []\n"
        "    evaluations = 0\n"
        "    for state in ranked_states:\n"
        "        if evaluations >= max_evaluations:\n"
        "            break\n"
        "        selected.append(state)\n"
        "        evaluations += 1\n"
        "    return selected\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read the supplied structured map and optimize a valid placement.",
    )
    kinds = {issue.kind for issue in issues}

    assert "fixed_structured_map_geometry" not in kinds
    assert "fixed_runtime_rule_vocabulary" not in kinds
    assert "fixed_ranked_search_shortlist" not in kinds


def test_skill_audit_allows_structured_map_symbolic_menu_declared_by_background_doc(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    environment = task_dir / "environment"
    data_dir = environment / "data"
    doc_dir = environment / "doc"
    data_dir.mkdir(parents=True)
    doc_dir.mkdir(parents=True)
    (data_dir / "runtime-map.Civ6Map").write_bytes(b"runtime structured map")
    (doc_dir / "civ6-public-rules.md").write_text(
        "Public specialty districts: CAMPUS, INDUSTRIAL_ZONE, HOLY_SITE, "
        "COMMERCIAL_HUB, HARBOR, THEATER_SQUARE.\n"
        "Public non-specialty districts: AQUEDUCT, DAM, CANAL, "
        "NEIGHBORHOOD.\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-map-optimizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "optimizer.py").write_text(
        "SPECIALTY_OPTIONS = ['CAMPUS', 'INDUSTRIAL_ZONE', 'HOLY_SITE', "
        "'COMMERCIAL_HUB', 'HARBOR', 'THEATER_SQUARE']\n"
        "NON_SPECIALTY_OPTIONS = ['AQUEDUCT', 'DAM', 'CANAL', "
        "'NEIGHBORHOOD']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read the supplied structured map and apply the frozen public rules.",
    )

    assert "fixed_runtime_rule_vocabulary" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_structured_map_menu_with_undeclared_input_symbol(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    environment = task_dir / "environment"
    data_dir = environment / "data"
    doc_dir = environment / "doc"
    data_dir.mkdir(parents=True)
    doc_dir.mkdir(parents=True)
    (data_dir / "runtime-map.Civ6Map").write_bytes(b"runtime structured map")
    (data_dir / "scenario.json").write_text(
        '{"available_district": "CURRENT_INSTANCE_DISTRICT"}',
        encoding="utf-8",
    )
    (doc_dir / "public-rules.md").write_text(
        "Public districts: CAMPUS and INDUSTRIAL_ZONE.\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-map-optimizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "optimizer.py").write_text(
        "DISTRICT_OPTIONS = ['CAMPUS', 'INDUSTRIAL_ZONE', "
        "'CURRENT_INSTANCE_DISTRICT']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read the supplied structured map and apply only public rules.",
    )

    assert "fixed_runtime_rule_vocabulary" in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_structured_map_symbolic_menu_not_in_public_contract(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "runtime-map.Civ6Map").write_bytes(b"runtime structured map")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-map-optimizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "optimizer.py").write_text(
        "DISTRICT_OPTIONS = ['CAMPUS', 'INDUSTRIAL_ZONE', 'HOLY_SITE']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read the supplied structured map and derive permitted rules at runtime.",
    )

    assert "fixed_runtime_rule_vocabulary" in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_ranked_shortlist_hidden_behind_default(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "runtime-map.Civ6Map").write_bytes(b"runtime structured map")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-map-optimizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "optimizer.py").write_text(
        "TOP_N = 3\n"
        "def top_positions(ranked_candidates, n=TOP_N):\n"
        "    return [candidate for candidate in ranked_candidates[:n]]\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read the supplied structured map and optimize a valid placement.",
    )

    assert "fixed_ranked_search_shortlist" in {issue.kind for issue in issues}


def test_skill_audit_allows_fixed_speaker_chunk_and_cluster_policy(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-speaker" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "diarize.py").write_text(
        "def run(large_chunk_size=100, small_chunk_size=10, chunk_size=2, "
        "window_size=10, close_th=2, len_th=10, max_k=10):\n"
        "    return large_chunk_size\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive VAD, chunking, and clustering policy from each recording.",
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_allows_vad_durations_and_hidden_chunk_constant(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-speaker" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "diarize.py").write_text(
        "def run(sample_rate, min_speech_ms=250, min_silence_ms=100, "
        "speech_pad_ms=30, activation_th=0.5, deactivation_th=1 / 4):\n"
        "    chunk_size = int(3.0 * sample_rate)\n"
        "    return chunk_size\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive VAD timing, chunking, and activation policy from each recording.",
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_allows_vad_policy_derived_from_runtime_evidence(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-speaker" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "diarize.py").write_text(
        "def run(sample_rate, runtime_seconds, evidence):\n"
        "    min_speech_ms = evidence['min_speech_ms']\n"
        "    min_silence_ms = evidence['min_silence_ms']\n"
        "    speech_pad_ms = evidence['speech_pad_ms']\n"
        "    chunk_size = int(runtime_seconds * sample_rate)\n"
        "    activation_th = evidence.quantile()\n"
        "    return (min_speech_ms, min_silence_ms, speech_pad_ms, "
        "chunk_size, activation_th)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive VAD timing, chunking, and activation policy from runtime evidence.",
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_allows_fixed_track_frame_policy_aliases(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-tracking" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "track.py").write_text(
        "def run(min_track_frames=5, max_track_frames=120, "
        "track_min_frames=4, minimum_track_detections=3, "
        "short_track_length=6, track_lifespan_frames=90):\n"
        "    return min_track_frames\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive track persistence requirements from runtime FPS and evidence.",
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_allows_track_frames_derived_from_runtime_evidence(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-tracking" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "track.py").write_text(
        "def run(fps, runtime_seconds, evidence):\n"
        "    min_track_frames = int(fps * runtime_seconds)\n"
        "    track_min_frames = evidence.quantile()\n"
        "    short_track_length = evidence.short_track_cutoff()\n"
        "    return min_track_frames, track_min_frames, short_track_length\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive track persistence requirements from runtime FPS and evidence.",
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_allows_sampling_intervals_and_mixed_fixed_multipliers(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-tracking" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "track.py").write_text(
        "def run(sample_interval=2, frame_interval=3):\n"
        "    adaptive_thresh = max(runtime_threshold, box_scale * 4)\n"
        "    max_distance = min(runtime_distance, box_scale * 5)\n"
        "    return sample_interval, frame_interval, adaptive_thresh, max_distance\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Derive sampling cadence and geometric gates from runtime evidence.",
    )
    kinds = {issue.kind for issue in issues}
    assert "unjustified_fixed_policy" not in kinds
    assert "unjustified_fixed_threshold" not in kinds


def test_skill_audit_allows_runtime_or_public_sampling_and_multipliers(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-tracking" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "track.py").write_text(
        "def runtime_run(fps, runtime_seconds, runtime_multiplier):\n"
        "    sample_interval = int(fps * runtime_seconds)\n"
        "    adaptive_thresh = max(runtime_threshold, box_scale * runtime_multiplier)\n"
        "    return sample_interval, adaptive_thresh\n"
        "def public_run(sample_interval=2):\n"
        "    max_distance = min(runtime_distance, box_scale * 4)\n"
        "    return sample_interval, max_distance\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Use sampling interval 2 and distance multiplier 4 when configured; "
        "otherwise derive them from runtime evidence.",
    )
    kinds = {issue.kind for issue in issues}
    assert "unjustified_fixed_policy" not in kinds
    assert "unjustified_fixed_threshold" not in kinds


def test_skill_audit_allows_local_runtime_best_score_sentinel(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-search" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "search.py").write_text(
        "def choose(candidates, runtime_score):\n"
        "    best_quality_score = -1\n"
        "    best = None\n"
        "    for candidate in candidates:\n"
        "        candidate_score = runtime_score(candidate)\n"
        "        if candidate_score > best_quality_score:\n"
        "            best_quality_score = candidate_score\n"
        "            best = candidate\n"
        "    return best\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select the best candidate using runtime evidence.",
    )
    assert "unjustified_fixed_threshold" not in {issue.kind for issue in issues}


def test_skill_audit_allows_best_score_sentinel_used_as_acceptance_cutoff(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-search" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "search.py").write_text(
        "def choose(candidates, runtime_score):\n"
        "    best_quality_score = -1\n"
        "    for candidate in candidates:\n"
        "        candidate_score = runtime_score(candidate)\n"
        "        if candidate_score > best_quality_score:\n"
        "            best_quality_score = candidate_score\n"
        "    if best_quality_score > 0.75:\n"
        "        return True\n"
        "    return False\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select the best candidate using runtime evidence.",
    )
    assert "unjustified_fixed_threshold" not in {issue.kind for issue in issues}


def test_skill_audit_allows_unupdated_or_constant_best_score_sentinels(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-search" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "search.py").write_text(
        "def unupdated(candidates):\n"
        "    best_quality_score = -1\n"
        "    return best_quality_score\n"
        "def constant_update(candidates, runtime_score):\n"
        "    best_other_score = -1\n"
        "    for candidate in candidates:\n"
        "        candidate_score = runtime_score(candidate)\n"
        "        if candidate_score > best_other_score:\n"
        "            best_other_score = 0.8\n"
        "    return best_other_score\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Select the best candidate using runtime evidence.",
    )
    assert "unjustified_fixed_threshold" not in {issue.kind for issue in issues}


def test_skill_audit_allows_tracking_policy_declared_by_instruction_or_doc(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    doc_dir = task_dir / "environment" / "doc"
    doc_dir.mkdir(parents=True)
    (doc_dir / "tracking.md").write_text(
        "The public tracking configuration sets min_frames to 3.\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "tracker.py").write_text(
        "def track(max_distance=45, min_frames=3):\n"
        "    return max_distance, min_frames\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Use max_distance 45 and the public tracking configuration.",
    )
    assert "unjustified_fixed_policy" not in {issue.kind for issue in issues}


def test_skill_audit_rejects_current_aliases_and_spreadsheet_ranges(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "workbook.py").write_text(
        "known_prefixes = ['Czechia', 'Slovakia']\n"
        "formula = \"MATCH(2025, 'Total Reserves'!A10:A18, 0)\"\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Build the requested workbook for 2025 using labeled sections.",
    )
    kinds = {issue.kind for issue in issues}
    assert "fixed_instance_alias_table" in kinds
    assert "undeclared_spreadsheet_layout_literal" in kinds


def test_spreadsheet_address_gate_does_not_flag_precise_ass_syntax(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-subtitles"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Use [Script Info] and [V4.00+ Styles] sections. ASS colours use "
        "&H00FFFFFF and &H000000FF tokens.\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Write standards-compliant ASS subtitles.",
    )
    assert "undeclared_spreadsheet_layout_literal" not in {
        issue.kind for issue in issues
    }


def test_spreadsheet_address_gate_does_not_flag_python_regex_character_class(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-python" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "scan.py").write_text(
        "import re\n"
        "def attributes(content):\n"
        "    return re.findall(r'self\\.([a-zA-Z_][a-zA-Z0-9_]*)', content)\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Inspect Python attribute syntax.",
    )
    assert "undeclared_spreadsheet_layout_literal" not in {
        issue.kind for issue in issues
    }


def test_spreadsheet_address_gate_does_not_flag_csv_domain_identifiers(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "events.csv").write_text(
        "product_id,station_id\nX1,ST2\nR1,T1\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-normalizer" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "normalize.py").write_text(
        "DOMAIN_EXAMPLES = ['X1', 'ST2', 'R1', 'T1']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Normalize records from the supplied CSV codebook at runtime.",
    )
    assert "undeclared_spreadsheet_layout_literal" not in {
        issue.kind for issue in issues
    }


def test_spreadsheet_address_gate_still_checks_actual_workbook_inputs(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    _write_range_fixture_xlsx(data_dir / "template.xlsx")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-reserves" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "model.py").write_text(
        "TARGET_RANGE = 'M12:M20'\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Build the requested artifact from supplied runtime labels.",
    )
    assert "undeclared_spreadsheet_layout_literal" in {
        issue.kind for issue in issues
    }


def test_spreadsheet_address_gate_checks_public_excel_output_contract(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-model" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "model.py").write_text(
        "TARGET_CELL = 'M12'\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Create an Excel workbook from the supplied runtime records.",
    )
    assert "undeclared_spreadsheet_layout_literal" in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_serialized_current_source_patch(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    app_dir = task_dir / "environment" / "website" / "src"
    app_dir.mkdir(parents=True)
    source_lines = [
        "export async function loadCurrentCustomerProfile() {",
        "const customer = await fetchCurrentCustomerRecord();",
        "const purchases = await fetchCurrentPurchaseHistory();",
        "return renderCurrentCustomerDashboard(customer, purchases);",
    ]
    (app_dir / "page.ts").write_text("\n".join(source_lines), encoding="utf-8")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "patch.py").write_text(
        "PATCH = '''\n" + "\n".join(source_lines) + "\n'''\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, "Improve performance")
    assert "current_source_patch_overlap" in {issue.kind for issue in issues}


def test_skill_audit_rejects_mining_hidden_or_future_git_commits(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "import subprocess\n"
        "def extract_reference_patch(repo):\n"
        "    commits = subprocess.run(['git', '-C', repo, 'log', '--all', '--oneline'])\n"
        "    return subprocess.run(['git', '-C', repo, 'show', commits.stdout])\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose the checked-out failing repository from public build evidence.",
    )
    assert "current_repository_history_oracle" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_current_tree_git_operations(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "import subprocess\n"
        "def validate(repo, patch):\n"
        "    subprocess.run(['git', 'status', '--short'], cwd=repo)\n"
        "    subprocess.run(['git', 'diff', '--check'], cwd=repo)\n"
        "    return subprocess.run(['git', 'apply', '--check', patch], cwd=repo)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose the checked-out failing repository from public build evidence.",
    )
    assert "current_repository_history_oracle" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_git_wrapper_history_indirection(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "import subprocess\n"
        "def run_git(repo, *args):\n"
        "    return subprocess.run(['git'] + list(args), cwd=repo)\n\n"
        "def find_reference(repo, path, old_commit, new_commit):\n"
        "    history = run_git(repo, 'log', '--oneline', '--', path)\n"
        "    source = run_git(repo, 'show', old_commit + ':' + path)\n"
        "    return run_git(repo, 'diff', old_commit, new_commit, '--', path)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose the checked-out failing repository from public build evidence.",
    )
    assert "current_repository_history_oracle" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_publicly_prescribed_git_history_wrapper(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "import subprocess\n"
        "def run_git(repo, *args):\n"
        "    return subprocess.run(['git'] + list(args), cwd=repo)\n\n"
        "def inspect_release(repo):\n"
        "    return run_git(repo, 'show', 'HEAD~1:pyproject.toml')\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Use git show to inspect the previous public release configuration.",
    )
    assert "current_repository_history_oracle" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_unjustified_fixed_maven_dependency_version(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "dependency.py").write_text(
        "def choose_dependency(package):\n"
        "    if package.startswith('com.example.current'):\n"
        "        return {'groupId': 'com.example', 'artifactId': 'legacy-lib', "
        "'version': '18.0', 'scope': 'test'}\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Resolve dependencies using the checked-out project's public metadata.",
    )
    assert "unjustified_fixed_dependency_version" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_public_maven_dependency_version(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "dependency.py").write_text(
        "COORDINATE = {'groupId': 'com.example', 'artifactId': 'public-lib', "
        "'version': '18.0'}\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Use the publicly required dependency version 18.0.",
    )
    assert "unjustified_fixed_dependency_version" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_undeclared_exact_security_policy_replacement(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    doc_dir = task_dir / "environment" / "doc"
    doc_dir.mkdir(parents=True)
    (doc_dir / "background.md").write_text(
        "A security fix must keep request input from overriding trusted injection "
        "metadata. Inspect the installed framework API and validate both attack "
        "and legitimate requests; no implementation is prescribed.\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-security"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Use a two-layer fix: add `policyInput = PublicOption.FALSE` to every "
        "injected parameter, then validate the same exact replacement.\n",
        encoding="utf-8",
    )
    (scripts / "patch.py").write_text(
        "import re\n"
        "def patch(content):\n"
        "    return re.sub(r'@FrameworkInject', "
        "'@FrameworkInject(policyInput = PublicOption.FALSE)', content)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Repair the vulnerable service without breaking legitimate requests.",
    )
    assert "undeclared_exact_security_policy_replacement" in {
        issue.kind for issue in issues
    }


def test_fresh_no_seed_source_repair_allows_same_run_security_api_semantics(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    doc_dir = task_dir / "environment" / "doc"
    doc_dir.mkdir(parents=True)
    (doc_dir / "background.md").write_text(
        "Inspect public framework APIs and validate attack and control behavior.\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-security" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def patch(content):\n"
        "    return content.replace('@FrameworkInject', "
        "'@FrameworkInject(policyInput = PublicOption.FALSE)')\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Repair the vulnerable service from the current source code.",
        allow_fresh_run_source_knowledge=True,
    )
    assert "undeclared_exact_security_policy_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_runtime_derived_security_candidate_workflow(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-security" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def repair(repo, discover_controls, generate_candidates, behavior_test):\n"
        "    controls = discover_controls(repo)\n"
        "    for candidate in generate_candidates(controls):\n"
        "        if behavior_test(candidate, attack=True, controls=True):\n"
        "            candidate.apply(repo)\n"
        "            return candidate\n"
        "    raise RuntimeError('no runtime-derived candidate passed behavior tests')\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Repair the security vulnerability and preserve legitimate requests.",
    )
    assert "undeclared_exact_security_policy_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_name_heuristic_fixed_security_boolean(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-security" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def derive_restrictive_input_policy(api_name):\n"
        "    if 'use' in api_name.lower():\n"
        "        return 'false'\n"
        "    return 'true'\n\n"
        "def patch_security_source(source, api_name):\n"
        "    policy = derive_restrictive_input_policy(api_name)\n"
        "    return source.replace('POLICY', policy)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Repair the security vulnerability and preserve legitimate requests.",
    )
    assert "undeclared_exact_security_policy_replacement" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_boolean_candidates_selected_by_behavior(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-security" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def select_input_policy(repo, behavior_test):\n"
        "    for candidate in ('true', 'false'):\n"
        "        if behavior_test(repo, candidate, attack=True, controls=True):\n"
        "            return candidate\n"
        "    raise RuntimeError('no candidate passed runtime behavior tests')\n\n"
        "def patch_security_source(repo, source, behavior_test):\n"
        "    policy = select_input_policy(repo, behavior_test)\n"
        "    return source.replace('POLICY', policy)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Repair the security vulnerability and preserve legitimate requests.",
    )
    assert "undeclared_exact_security_policy_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_exact_security_policy_prescribed_by_contract(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-security" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "patch.py").write_text(
        "def patch(content):\n"
        "    return content.replace('@FrameworkInject', "
        "'@FrameworkInject(policyInput = PublicOption.FALSE)')\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Fix the security issue by setting policyInput = PublicOption.FALSE.",
    )
    assert "undeclared_exact_security_policy_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_undeclared_fixed_api_source_replacement(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def repair(repo):\n"
        "    old_api = 'legacy.framework.annotations.GeneratedMarker'\n"
        "    new_api = 'modern.framework.processing.GeneratedMarker'\n"
        "    return replace_in_source(repo, old_api, new_api)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the Java build from its runtime compiler output.",
    )
    assert "undeclared_exact_source_replacement" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_runtime_derived_api_source_replacement(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def repair(repo, compiler_output):\n"
        "    old_api, new_api = diagnose_missing_api(compiler_output, repo)\n"
        "    return replace_in_source(repo, old_api, new_api)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the Java build from its runtime compiler output.",
    )
    assert "undeclared_exact_source_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_publicly_prescribed_api_source_replacement(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "def repair(repo):\n"
        "    old_api = 'legacy.framework.annotations.GeneratedMarker'\n"
        "    new_api = 'modern.framework.processing.GeneratedMarker'\n"
        "    return replace_in_source(repo, old_api, new_api)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Replace legacy.framework.annotations.GeneratedMarker with "
        "modern.framework.processing.GeneratedMarker to repair the build.",
    )
    assert "undeclared_exact_source_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_fixed_nested_api_migration_registry(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "API_RELOCATIONS = {\n"
        "    'legacy.framework': {\n"
        "        'GeneratedMarker': 'modern.framework.processing.GeneratedMarker',\n"
        "    },\n"
        "}\n\n"
        "def repair(repo, compiler_output):\n"
        "    old_api, new_api = lookup_relocation(compiler_output, API_RELOCATIONS)\n"
        "    return replace_in_source(repo, old_api, new_api)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the Java build from runtime compiler output.",
    )
    assert "undeclared_exact_source_replacement" in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_contract_prescribed_api_migration_registry(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "API_RELOCATIONS = {\n"
        "    'legacy.framework.GeneratedMarker': "
        "'modern.framework.processing.GeneratedMarker',\n"
        "}\n\n"
        "def repair(repo, compiler_output):\n"
        "    old_api, new_api = lookup_relocation(compiler_output, API_RELOCATIONS)\n"
        "    return replace_in_source(repo, old_api, new_api)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Replace legacy.framework.GeneratedMarker with "
        "modern.framework.processing.GeneratedMarker when the compiler reports it.",
    )
    assert "undeclared_exact_source_replacement" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_generated_patch_for_undeclared_current_source_target(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    app_dir = task_dir / "environment" / "repo" / "src"
    app_dir.mkdir(parents=True)
    (app_dir / "GuiceAnnotationIntrospector.java").write_text(
        "public class GuiceAnnotationIntrospector {\n"
        "  public Object findInjectableValue(Object member) { return null; }\n"
        "}\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "patch_generator.py").write_text(
        "TARGET = 'src/GuiceAnnotationIntrospector.java'\n"
        "REPLACEMENT = 'return JacksonInject.Value.construct(id, false);'\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Repair the vulnerable repository after diagnosing it at runtime.",
    )
    assert "undeclared_current_source_target" in {issue.kind for issue in issues}


def test_skill_audit_allows_source_target_declared_by_instruction(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    app_dir = task_dir / "environment" / "repo" / "src"
    app_dir.mkdir(parents=True)
    (app_dir / "DeclaredTarget.java").write_text(
        "public class DeclaredTarget {}\n", encoding="utf-8"
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "inspect.py").write_text(
        "TARGET = 'src/DeclaredTarget.java'\n", encoding="utf-8"
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Inspect src/DeclaredTarget.java and report its public API.",
    )
    assert "undeclared_current_source_target" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_rejects_rare_current_source_identifier_cluster(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    source_dir = task_dir / "environment" / "repo"
    source_dir.mkdir(parents=True)
    (source_dir / "client.py").write_text(
        "class Client:\n"
        "    def start(self, tags):\n"
        "        self._tags_for_future_session = tags\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "When initialization fails, move `_tags_for_future_session` before the guard.\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the failing repository at runtime.",
    )
    assert "current_source_identifier_cluster" in {
        issue.kind for issue in issues
    }


def test_fresh_no_seed_source_repair_allows_same_run_source_identifiers(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    source_dir = task_dir / "environment" / "repo"
    source_dir.mkdir(parents=True)
    (source_dir / "client.py").write_text(
        "class Client:\n"
        "    def start(self, tags):\n"
        "        self._tags_for_future_session = tags\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Diagnose `_tags_for_future_session` from the current checkout.\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the failing source-code repository at runtime.",
        allow_fresh_run_source_knowledge=True,
    )
    assert "current_source_identifier_cluster" not in {
        issue.kind for issue in issues
    }


def test_source_knowledge_opt_in_requires_a_source_repair_contract(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    source_dir = task_dir / "environment" / "repo"
    source_dir.mkdir(parents=True)
    (source_dir / "records.py").write_text(
        "CURRENT_CUSTOMER_IDENTIFIER = 'account'\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-report"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Always select CURRENT_CUSTOMER_IDENTIFIER for this report.\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Summarize the supplied business records.",
        allow_fresh_run_source_knowledge=True,
    )
    assert "current_source_identifier_cluster" in {
        issue.kind for issue in issues
    }


def test_source_knowledge_opt_in_keeps_current_input_and_exact_replacement_gates(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "records.csv").write_text(
        "record_id\nCASE_CURRENT_9087\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-build" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "CURRENT_ID = 'CASE_CURRENT_9087'\n"
        "OLD = 'legacy.framework.GeneratedMarker'\n"
        "NEW = 'modern.framework.GeneratedMarker'\n"
        "def repair(repo):\n"
        "    return replace_in_source(repo, OLD, NEW)\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the failing source-code repository.",
        allow_fresh_run_source_knowledge=True,
    )
    kinds = {issue.kind for issue in issues}
    assert "current_input_value" in kinds
    assert "undeclared_exact_source_replacement" in kinds


def test_skill_audit_rejects_single_current_identifier_in_patch_treatment(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    source_dir = task_dir / "environment" / "repo"
    source_dir.mkdir(parents=True)
    (source_dir / "event.py").write_text(
        "class Event:\n"
        "    def finish(self):\n"
        "        self.end_timestamp = now()\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "repair.py").write_text(
        "import re\n"
        "def patch(content):\n"
        "    fixed = re.sub(r'end_timestamp = now\\(\\)', 'end_timestamp = None', content)\n"
        "    return fixed\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose and repair the failing repository at runtime.",
    )
    assert "current_source_identifier_cluster" in {
        issue.kind for issue in issues
    }


def test_skill_audit_uses_container_identifier_snapshot_and_allows_public_terms(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    doc_dir = task_dir / "environment" / "doc"
    doc_dir.mkdir(parents=True)
    (doc_dir / "background.md").write_text(
        "A public framework may expose PublicInjectionPolicy as documented API.\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "Use PublicInjectionPolicy generally. For this repair, target "
        "GuiceAnnotationIntrospector and findInjectableValue.\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Diagnose injection precedence from runtime evidence.",
        current_source_identifiers={
            "PublicInjectionPolicy": "src/PublicApi.java",
            "GuiceAnnotationIntrospector": "src/GuiceAnnotationIntrospector.java",
            "findInjectableValue": "src/GuiceAnnotationIntrospector.java",
            "subprocess": "src/utility.py",
        },
    )
    identifier_issues = [
        issue for issue in issues
        if issue.kind == "current_source_identifier_cluster"
    ]
    assert len(identifier_issues) == 1
    assert "GuiceAnnotationIntrospector" in identifier_issues[0].evidence
    assert "findInjectableValue" in identifier_issues[0].evidence
    assert "PublicInjectionPolicy" not in identifier_issues[0].evidence
    assert "subprocess" not in identifier_issues[0].evidence


def test_skill_audit_allows_public_unified_planning_api_vocabulary(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    doc_dir = task_dir / "environment" / "doc"
    doc_dir.mkdir(parents=True)
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-pddl-planner" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "planner.py").write_text(
        "from unified_planning.io import PDDLReader\n"
        "from unified_planning.shortcuts import OneshotPlanner, PlanValidator\n"
        "def solve(domain_path, problem_path, output_path):\n"
        "    reader = PDDLReader()\n"
        "    problem = reader.parse_problem(domain_path, problem_path)\n"
        "    with OneshotPlanner(problem_kind=problem.kind) as planner:\n"
        "        result = planner.solve(problem)\n"
        "    with PlanValidator(problem_kind=problem.kind) as validator:\n"
        "        validator.validate(problem, result.plan)\n"
        "    output_path.write_text(str(result.plan))\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Generate valid plans from supplied PDDL domain and problem files.",
        current_source_identifiers={
            "unified_planning": "validate.py",
            "OneshotPlanner": "validate.py",
            "PlanValidator": "validate.py",
            "parse_problem": "validate.py",
            "validate_plan": "validate.py",
            "problem_kind": "validate.py",
        },
    )
    assert "current_source_identifier_cluster" not in {
        issue.kind for issue in issues
    }


def test_container_identifier_snapshot_runs_before_boundary_audit() -> None:
    audit_source = inspect.getsource(
        HarborTerminus2Evolution._audit_exported_evolved_skills
    )
    snapshot = audit_source.index("_container_current_source_identifiers")
    audit = audit_source.index("audit_evolved_skill_directory")
    assert snapshot < audit

    exit_source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    boundary = exit_source.index("_audit_exported_evolved_skills")
    surrogate = exit_source.index("Running surrogate verifier")
    assert boundary < surrogate

    run_source = inspect.getsource(HarborTerminus2Evolution.run)
    frozen_snapshot = run_source.index(
        "self._initial_container_source_identifiers = ("
    )
    agent_execution = run_source.index("await super().run")
    assert frozen_snapshot < agent_execution


def test_boundary_audit_uses_frozen_pre_execution_identifier_snapshot() -> None:
    audit_source = inspect.getsource(
        HarborTerminus2Evolution._audit_exported_evolved_skills
    )
    frozen_snapshot = audit_source.index("_initial_container_source_identifiers")
    fallback_scan = audit_source.index("_container_current_source_identifiers")
    assert frozen_snapshot < fallback_scan


def test_fresh_claude_trace_rejects_manual_edit_after_skill_helper_failure(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-example"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": "python /app/environment/skills/evo-example/scripts/run.py"},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": True, "content": "SyntaxError",
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "edit-1", "name": "Edit",
                "input": {"file_path": "/app/src/current.ts"},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-example"}
    )
    assert violation is not None
    assert "Edit" in violation


def test_fresh_claude_trace_accepts_successful_evolved_helper(tmp_path: Path) -> None:
    trace = tmp_path / "claude-code.txt"
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-example"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": "python /app/environment/skills/evo-example/scripts/run.py"},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "validation passed",
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    assert HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-example"}
    ) is None


@pytest.mark.parametrize(
    "history_command",
    [
        "git show 388101a:agentops/__init__.py",
        "git diff 388101a..HEAD -- agentops/__init__.py",
    ],
)
def test_fresh_claude_trace_rejects_manual_repository_history_oracle(
    tmp_path: Path,
    history_command: str,
) -> None:
    trace = tmp_path / "claude-code.txt"
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-example"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": "python /app/environment/skills/evo-example/scripts/run.py"},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "validation passed",
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-2", "name": "Bash",
                "input": {"command": history_command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-example"}
    )
    assert violation is not None
    assert violation.startswith("manual_repository_history_oracle")


@pytest.mark.parametrize(
    "command",
    [
        "git status --short",
        "git diff --check",
        "git diff --name-only HEAD",
    ],
)
def test_repository_history_gate_allows_current_checkout_inspection(
    command: str,
) -> None:
    assert not HarborTerminus2Evolution._manual_repository_history_oracle(command)


def test_repository_history_gate_allows_publicly_prescribed_history_operation() -> None:
    assert not HarborTerminus2Evolution._manual_repository_history_oracle(
        "git show HEAD~1:pyproject.toml",
        "Use git show to inspect the previous public release, then repair the build.",
    )
    assert HarborTerminus2Evolution._manual_repository_history_oracle(
        "git show HEAD~1:pyproject.toml",
        "Do not use git show; diagnose only from the current checkout.",
    )


def test_fresh_claude_trace_rejects_manual_instance_target_list(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/app/environment/skills/evo-pdf/scripts')
from utils import run_anonymization
paper_extra_targets = [
    {'text': 'Current Author One', 'pages': 'before_refs'},
    {'text': 'Current University', 'pages': 'before_refs'},
    {'text': 'CURRENT-GRANT-12345', 'pages': [0]},
    {'text': 'Current Conference 2026', 'pages': [0]},
]
run_anonymization('/root/input.pdf', '/root/output.pdf', paper_extra_targets)
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-pdf"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "done",
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-pdf"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_target_fallback")


def test_fresh_claude_trace_rejects_manual_unit_registry_fallback(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/app/environment/skills/evo-unit/scripts')
from utils import apply_conversion_registry
suspect = {
    'CurrentFeatureAlpha': {'ranges': [(0, 3), (3, 20)], 'note': 'unit-a to unit-b'},
    'CurrentFeatureBeta': {'ranges': [(0, 8), (8, 50)], 'note': 'unit-c to unit-d'},
    'CurrentFeatureGamma': {'ranges': [(0, 2), (2, 80)], 'note': 'unit-e to unit-f'},
}
apply_conversion_registry('/root/input.csv', '/root/output.csv', suspect)
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-unit"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "done",
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-unit"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_target_fallback")


def test_fresh_claude_trace_allows_runtime_paths_and_generic_configuration(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import os, sys
sys.path.insert(0, '/app/environment/skills/evo-example/scripts')
from run import execute
input_paths = ['/root/one.pdf', '/root/two.pdf']
build_args = ['--quiet', '--validate', '--preserve-metadata']
extra_targets = discover_targets(input_paths)
execute(input_paths, '/root/output', build_args, extra_targets)
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-example"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "validated",
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    assert HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-example"}
    ) is None


def test_fresh_claude_trace_rejects_manual_coordinate_placement_list(
    tmp_path: Path,
) -> None:
    """Regression: the Civ caller must not hand the low-level Skill a solved layout."""
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/root/.claude/skills/evo-civ/scripts')
from placement import can_place_district
city_center = (23, 13)
placed = [
    ('CAMPUS', (21, 14)),
    ('COMMERCIAL_HUB', (22, 14)),
    ('INDUSTRIAL_ZONE', (23, 14)),
    ('AQUEDUCT', (24, 14)),
    ('DAM', (23, 15)),
    ('SPACEPORT', (22, 13)),
    ('NEIGHBORHOOD', (22, 15)),
]
print(all(can_place_district(*position) for _district, position in placed))
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-civ"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-civ"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_target_fallback")


@pytest.mark.parametrize(
    "import_line, search_expression",
    [
        ("from itertools import combinations", "combinations(districts, 3)"),
        ("from itertools import product as cartesian", "cartesian(*positions)"),
        ("import itertools as it", "it.permutations(districts)"),
    ],
)
def test_fresh_claude_trace_rejects_caller_combinatorial_skill_search(
    tmp_path: Path,
    import_line: str,
    search_expression: str,
) -> None:
    """Regression: a fresh caller may not become the current-instance optimizer."""
    trace = tmp_path / "claude-code.txt"
    command = f"""python3 << 'PYEOF'
import sys
sys.path.insert(0, '/root/.claude/skills/evo-civ/scripts')
from placement import can_place_district
{import_line}
districts = discover_districts('/data/scenario.json')
positions = discover_positions('/data/scenario.json')
for candidate in {search_expression}:
    if can_place_district(candidate):
        print(candidate)
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-civ"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-civ"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_target_fallback")


def test_solution_search_gate_allows_one_end_to_end_optimizer_call() -> None:
    command = """python3 << 'PYEOF'
from evo_civ import solve_scenario
solve_scenario('/data/scenario.json', '/output/scenario.json')
PYEOF"""
    assert not HarborTerminus2Evolution._manual_instance_solution_search_fallback(
        command
    )


def test_fresh_claude_trace_rejects_caller_map_feature_inventory(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/root/.claude/skills/evo-civ/scripts')
from map_parser import parse_civ6_map
from hex_utils import get_neighbors
from placement import can_place_city_center
map_data = parse_civ6_map('/data/maps/runtime.Civ6Map')
for y in range(map_data['height']):
    for x in range(map_data['width']):
        if can_place_city_center(x, y, map_data):
            print((x, y), get_neighbors(x, y, map_data))
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-civ"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-civ"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_inspection_fallback")


def test_fresh_claude_trace_rejects_caller_pdf_identity_discovery(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/app/environment/skills/evo-paper/scripts')
from pdf_tools import extract_text_by_page, get_text_spans, discover_identifying_info
for path in ['/root/paper-a.pdf', '/root/paper-b.pdf']:
    pages = extract_text_by_page(path)
    spans = get_text_spans(path)
    print(discover_identifying_info(pages, spans))
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-paper"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-paper"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_inspection_fallback")


def test_fresh_claude_trace_rejects_python_c_pdf_identity_discovery(
    tmp_path: Path,
) -> None:
    """Regression: Python -c must not bypass low-level Skill ownership."""
    trace = tmp_path / "claude-code.txt"
    command = (
        "python3 -c \"import sys; "
        "sys.path.insert(0, '/root/.claude/skills/evo-pdf-anonymize/scripts'); "
        "from utils import extract_text_by_page, get_metadata, "
        "discover_identifying_info; "
        "papers=['paper1.pdf','paper2.pdf','paper3.pdf']; "
        "results=[(extract_text_by_page(p), get_metadata(p), "
        "discover_identifying_info(p)) for p in papers]; print(results)\""
    )
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-pdf-anonymize"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-pdf-anonymize"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_inspection_fallback")


def test_low_level_inspection_gate_allows_single_output_producing_extractor() -> None:
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/app/environment/skills/evo-formulas/scripts')
from pipeline import extract_formulas
extract_formulas('/root/input.pdf', '/root/output.json')
PYEOF"""
    assert not HarborTerminus2Evolution._manual_low_level_skill_inspection(command)


def test_low_level_inspection_gate_allows_non_skill_output_validation() -> None:
    command = """python3 << 'PYEOF'
import csv
from pathlib import Path
rows = list(csv.DictReader(Path('/root/output.csv').open()))
for row in rows:
    assert int(row['count']) >= 0
PYEOF"""
    assert not HarborTerminus2Evolution._manual_low_level_skill_inspection(command)


def test_fresh_claude_trace_rejects_caller_low_level_build_mutations(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/root/.claude/skills/evo-build/scripts')
from utils import add_dependency, add_property, add_invoker_exclusion
repo = '/home/travis/build/failed/example/project'
add_dependency(repo + '/value/pom.xml', 'javax.annotation', 'javax.annotation-api', '1.3.2')
add_property(repo + '/pom.xml', 'project.build.sourceEncoding', 'UTF-8')
add_invoker_exclusion(repo + '/value/src/it/functional/pom.xml', 'gwtserializer')
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-build"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-build"}, "Fix the build using runtime diagnostics."
    )
    assert violation is not None
    assert violation.startswith("manual_instance_mutation_fallback")


def test_low_level_mutation_gate_allows_one_end_to_end_repair() -> None:
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/root/.claude/skills/evo-build/scripts')
from utils import run_end_to_end, validate_result
run_end_to_end('/home/travis/build/failed/example/project')
validate_result('/home/travis/build/failed/example/project')
PYEOF"""
    assert not HarborTerminus2Evolution._manual_low_level_skill_mutation(command)


def test_mario_reward_one_trace_replay_rejects_caller_artifact_construction(
    tmp_path: Path,
) -> None:
    """Regression: low-level Skill imports plus caller CSV writing are not treatment."""
    trace = tmp_path / "claude-code.txt"
    command = """python3 << 'PYEOF'
import sys
sys.path.insert(0, '/app/environment/skills/evo-mario-counter/scripts')
from utils import load_gray, get_detections, bgr_l2
import pandas as pd
GRAY_THRESH = 0.6
COLOR_DIST_THRESH = 30.0
results = []
for frame_id in runtime_frames:
    results.append({'frame_id': frame_id, 'coins': 0})
df = pd.DataFrame(results)
df.to_csv('/root/counting_results.csv', index=False)
PYEOF"""
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-mario-counter"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "CSV written",
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-mario-counter"}
    )
    assert violation is not None
    assert violation.startswith("manual_artifact_construction_fallback")


def test_paper_reward_one_trace_replay_rejects_shell_identity_inventory(
    tmp_path: Path,
) -> None:
    """Regression: a caller-authored current author/grant grep list is not Skill use."""
    trace = tmp_path / "claude-code.txt"
    command = (
        "pdftotext /root/redacted/paper.pdf - | "
        "grep -n -i -E 'acknowledg|Current Author|Current University|"
        "CURRENT-GRANT-12345|Current Conference|author@example.org'"
    )
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-pdf-anonymizer"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": command},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-pdf-anonymizer"}
    )
    assert violation is not None
    assert violation.startswith("manual_instance_target_fallback")


def test_trace_gate_allows_end_to_end_helper_output_path_and_generic_grep() -> None:
    helper_command = """python3 << 'PYEOF'
from evo_example import run_end_to_end
run_end_to_end('/root/input.csv', '/root/output.csv')
PYEOF"""
    generic_audit = (
        "grep -E 'author|affiliation|email|doi|arxiv|acknowledgement' "
        "/root/output.txt"
    )

    assert not HarborTerminus2Evolution._manual_direct_artifact_construction(
        helper_command
    )
    assert not HarborTerminus2Evolution._manual_shell_identity_target_fallback(
        generic_audit
    )


def test_shell_identity_gate_allows_explicit_public_contract_tokens() -> None:
    command = "grep -E 'Alpha Lab|Beta University|Gamma Grant|Delta Venue' output.txt"
    contract = (
        "Check Alpha Lab, Beta University, Gamma Grant, and Delta Venue in the output."
    )
    assert not HarborTerminus2Evolution._manual_shell_identity_target_fallback(
        command,
        contract,
    )


def test_fresh_claude_trace_rejects_manual_exact_replacement_primitive(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-build"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": (
                    "python3 -c \"from run_fix import run_end_to_end; "
                    "print(run_end_to_end('/runtime/repo'))\""
                )},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "partial fix",
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-2", "name": "Bash",
                "input": {"command": (
                    "python3 -c \"from run_fix import replace_in_java_files; "
                    "old_import = 'import legacy.annotation.Generated;'; "
                    "new_import = 'import modern.processing.Generated;'; "
                    "replace_in_java_files('/runtime/repo', old_import, new_import)\""
                )},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )

    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-build"}
    )
    assert violation is not None
    assert violation.startswith("manual_exact_replacement_fallback")


def test_exact_replacement_gate_allows_runtime_derived_or_public_pair() -> None:
    runtime_command = (
        "old_import = parse_compiler_error(log); "
        "new_import = resolve_project_metadata(repo, old_import); "
        "replace_in_java_files(repo, old_import, new_import)"
    )
    assert not HarborTerminus2Evolution._manual_exact_replacement_fallback(
        runtime_command
    )

    public_command = (
        "old_import = 'legacy.annotation.Generated'; "
        "new_import = 'modern.processing.Generated'; "
        "replace_in_java_files(repo, old_import, new_import)"
    )
    assert not HarborTerminus2Evolution._manual_exact_replacement_fallback(
        public_command,
        "Replace legacy.annotation.Generated with modern.processing.Generated.",
    )


def test_fresh_claude_trace_rejects_manual_environment_fallback_after_failure(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-example"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": "python /app/environment/skills/evo-example/scripts/run.py"},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": True, "content": "ModuleNotFoundError: rich",
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-2", "name": "Bash",
                "input": {"command": "pip install --break-system-packages rich"},
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    violation = HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-example"}
    )
    assert violation is not None
    assert violation.startswith("manual_environment_fallback")


def test_fresh_claude_trace_allows_helper_encapsulated_environment_setup(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "claude-code.txt"
    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "skill-1", "name": "Skill",
                "input": {"skill": "evo-example"},
            }]},
        },
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use", "id": "bash-1", "name": "Bash",
                "input": {"command": "python /app/environment/skills/evo-example/scripts/setup_and_run.py"},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result", "tool_use_id": "bash-1",
                "is_error": False, "content": "setup and validation passed",
            }]},
        },
    ]
    trace.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    assert HarborTerminus2Evolution._claude_trace_execution_violation(
        trace, {"evo-example"}
    ) is None


def test_skill_audit_rejects_precise_current_input_numbers(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "measurements.json").write_text(
        '{"capital": 264125.56, "ratio": 0.043566}', encoding="utf-8"
    )
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "utils.py").write_text(
        "# current capital 264125.56 and derived ratio 0.043566\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, "Analyze capital")
    evidence = [issue.evidence for issue in issues if issue.kind == "current_input_value"]
    assert any("264125.56" in item for item in evidence)
    assert any("0.043566" in item for item in evidence)


def test_skill_audit_rejects_current_artifact_paths_in_executable_code(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    environment = task_dir / "environment"
    environment.mkdir(parents=True)
    (environment / "population.pdf").write_bytes(b"synthetic")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run_all.py").write_text(
        "from pathlib import Path\n"
        "def run(input_path='/root/population.pdf'):\n"
        "    output = Path('/root/demographic_analysis.xlsx')\n"
        "    return input_path, output\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read /root/population.pdf and save /root/demographic_analysis.xlsx",
    )
    path_issues = [
        issue for issue in issues if issue.kind == "current_artifact_path_literal"
    ]
    assert len(path_issues) == 2
    assert all("caller argument" in issue.evidence for issue in path_issues)


def test_skill_audit_allows_parameterized_artifact_paths(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    environment = task_dir / "environment"
    environment.mkdir(parents=True)
    (environment / "population.pdf").write_bytes(b"synthetic")
    skill_root = tmp_path / "skills"
    scripts = skill_root / "evo-example" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run_all.py").write_text(
        "from pathlib import Path\n"
        "def run(input_path, output_dir):\n"
        "    index = Path(output_dir) / 'index.html'\n"
        "    script = Path(output_dir) / 'js' / 'visualization.js'\n"
        "    return input_path, index, script\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Read /root/population.pdf and write /root/output/index.html plus "
        "/root/output/js/visualization.js",
    )
    assert "current_artifact_path_literal" not in {issue.kind for issue in issues}


def test_skill_audit_rejects_undeclared_current_input_in_manifest_example(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    video_dir = task_dir / "environment" / "video"
    video_dir.mkdir(parents=True)
    (video_dir / "example.mp4").write_bytes(b"synthetic")
    (video_dir / "heldout.mp4").write_bytes(b"synthetic")
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "utils.py").write_text(
        "def validate(input_dir, expected_files):\n"
        "    return input_dir, expected_files\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "```python\n"
        "from utils import validate\n"
        "validate('/root/video', ['example.mp4', 'heldout.mp4'])\n"
        "```\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Process the example at /root/video/example.mp4 and discover other inputs.",
    )
    manifest_issues = [
        issue
        for issue in issues
        if issue.kind == "undeclared_current_artifact_manifest_literal"
    ]
    assert len(manifest_issues) == 1
    assert "heldout.mp4" in manifest_issues[0].evidence


def test_skill_audit_allows_instruction_declared_manifest_paths(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    video_dir = task_dir / "environment" / "video"
    video_dir.mkdir(parents=True)
    (video_dir / "example.mp4").write_bytes(b"synthetic")
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "utils.py").write_text(
        "def run(input_path):\n    return input_path\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "```python\nfrom utils import run\nrun('/root/video/example.mp4')\n```\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Process /root/video/example.mp4.",
    )
    assert "undeclared_current_artifact_manifest_literal" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_allows_instruction_numbers_and_runtime_derivation(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "Derive values at runtime.\n"
        "```python\nfrom utils import close\nclose(1, 1)\n```\n",
        encoding="utf-8",
    )
    (scripts / "utils.py").write_text(
        "def close(a, b, tolerance=0.01):\n    return abs(a-b) <= tolerance\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Use a 0.01 tolerance.",
    )
    assert not issues


def test_skill_audit_allows_instruction_stated_schema_spelling(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    data_dir = task_dir / "environment" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "vendors.csv").write_text(
        "vendor_id,vendor_name\nV001,Synthetic Vendor\n",
        encoding="utf-8",
    )
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "```python\nfrom utils import read_row\nread_row({})\n```\n",
        encoding="utf-8",
    )
    (scripts / "utils.py").write_text(
        "def read_row(row):\n    return row['vendor_id']\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "The vendor file contains a Vendor ID field.",
    )
    assert not issues


def test_skill_audit_rejects_fresh_example_with_caller_implemented_helper(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "utils.py").write_text(
        "def run_task(input_path, output_path, config):\n"
        "    return output_path\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "```python\n"
        "import sys\n"
        "sys.path.insert(0, '/app/environment/skills/evo-example/scripts')\n"
        "from utils import run_task\n"
        "config = build_domain_config()  # caller implements this\n"
        "run_task('/root/input.csv', '/root/output.csv', config)\n"
        "```\n",
        encoding="utf-8",
    )

    kinds = {
        issue.kind
        for issue in audit_evolved_skill_directory(
            skill_root, task_dir, "Process the runtime input"
        )
    }
    assert "documented_example_unresolved_name" in kinds


def test_skill_audit_rejects_missing_or_import_only_documented_api(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "```python\nfrom utils import solve, validate_output\n```\n",
        encoding="utf-8",
    )
    (scripts / "utils.py").write_text(
        "def solve(input_path, output_path):\n    return output_path\n",
        encoding="utf-8",
    )

    issues = audit_evolved_skill_directory(skill_root, task_dir, "Process input")
    kinds = {issue.kind for issue in issues}
    assert "documented_api_missing" in kinds
    assert "documented_api_not_invoked" in kinds


def test_skill_audit_accepts_documented_end_to_end_calls(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-example"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-example\ndescription: example\n---\n"
        "```python\n"
        "from utils import solve, validate_output\n"
        "solve('/input', '/output')\n"
        "validate_output('/output')\n"
        "```\n",
        encoding="utf-8",
    )
    (scripts / "utils.py").write_text(
        "def solve(input_path, output_path):\n    return output_path\n\n"
        "def validate_output(output_path):\n    return True\n",
        encoding="utf-8",
    )

    assert not audit_evolved_skill_directory(
        skill_root,
        task_dir,
        "Process input",
    )


def test_skill_audit_rejects_apply_entrypoint_that_only_analyzes_and_advises(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-react"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-react\ndescription: apply performance repairs\n---\n"
        "```python\nfrom perf_fixer import apply_all_fixes\n"
        "apply_all_fixes('/app')\n```\n",
        encoding="utf-8",
    )
    (scripts / "perf_fixer.py").write_text(
        "def analyze_app(app_dir):\n"
        "    with open(app_dir + '/src/app/page.tsx') as source:\n"
        "        return source.read()\n\n"
        "def apply_all_fixes(app_dir):\n"
        "    issues = analyze_app(app_dir)\n"
        "    print('Apply fixes using patterns documented in SKILL.md')\n"
        "    return issues\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, "Fix the app")
    assert "documented_treatment_not_executable" in {
        issue.kind for issue in issues
    }


def test_skill_audit_accepts_apply_wrapper_with_local_writer(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-rewriter"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-rewriter\ndescription: apply reusable repairs\n---\n"
        "```python\nfrom fixer import apply_fixes, validate_fix\n"
        "apply_fixes('/workspace')\nvalidate_fix('/workspace')\n```\n",
        encoding="utf-8",
    )
    (scripts / "fixer.py").write_text(
        "def rewrite(path, content):\n"
        "    with open(path, 'w') as destination:\n"
        "        destination.write(content)\n\n"
        "def apply_fixes(root):\n"
        "    rewrite(root + '/result.txt', 'derived at runtime')\n\n"
        "def validate_fix(root):\n"
        "    return True\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, "Fix the workspace")
    assert "documented_treatment_not_executable" not in {
        issue.kind for issue in issues
    }


def test_skill_audit_accepts_treatment_writer_imported_inside_entrypoint(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "task"
    (task_dir / "environment" / "data").mkdir(parents=True)
    skill_root = tmp_path / "skills"
    skill_dir = skill_root / "evo-runner"
    scripts = skill_dir / "scripts"
    scripts.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: evo-runner\ndescription: run reusable repairs\n---\n"
        "```python\nfrom run_task import run\nrun('/workspace')\n```\n",
        encoding="utf-8",
    )
    (scripts / "run_task.py").write_text(
        "def run(root):\n"
        "    from utils import rewrite\n"
        "    rewrite(root + '/result.txt')\n",
        encoding="utf-8",
    )
    (scripts / "utils.py").write_text(
        "def rewrite(path):\n"
        "    with open(path, 'w') as destination:\n"
        "        destination.write('runtime-derived')\n",
        encoding="utf-8",
    )
    issues = audit_evolved_skill_directory(skill_root, task_dir, "Fix workspace")
    assert "documented_treatment_not_executable" not in {
        issue.kind for issue in issues
    }


def test_adversarial_verifier_context_has_no_hidden_details() -> None:
    verifier = IndependentVerifier("test-model")
    environment = _Environment([_Result("def test_public_requirement():\n    assert True\n")])
    context = asyncio.run(
        verifier._build_previous_verifier_context(
            environment,
            adversarial_recheck=True,
        )
    )

    assert "hidden evaluation rejected" in context
    assert "NOT given hidden tests" in context
    assert "public task instruction" in context
    assert "expected answers" in context


def test_previous_verifier_context_ignores_interactive_shell_noise() -> None:
    verifier = IndependentVerifier("test-model")
    environment = _Environment(
        [
            _Result(
                "bash: cannot set terminal process group: Inappropriate ioctl\n"
                "bash: no job control in this shell\n"
                "__SKILL_VERIFIER_BEGIN__\n"
                "__SKILL_VERIFIER_END__\n"
            )
        ]
    )
    context = asyncio.run(verifier._build_previous_verifier_context(environment))
    assert context.startswith("No previous verifier script exists")
    assert "job control" not in context


def test_independent_verifier_log_audit_rejects_candidate_pipeline(tmp_path: Path) -> None:
    response_dir = tmp_path / "episode-3"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        '{"commands":[{"keystrokes":"from run_pipeline import run_pipeline\\n"}]}',
        encoding="utf-8",
    )

    violations = IndependentVerifier._audit_verifier_logs(tmp_path)

    assert violations == ["episode-3: imported candidate pipeline"]


def test_independent_verifier_log_audit_allows_read_only_output_checks(tmp_path: Path) -> None:
    response_dir = tmp_path / "episode-1"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        '{"commands":[{"keystrokes":"python3 -m pytest '
        '/root/verifier/test_outputs.py -q\\n"}]}',
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_verifier_logs(tmp_path) == []


def test_coordinate_methodology_audit_rejects_current_artifact_first(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-1"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        json.dumps(
            {
                "commands": [
                    {"keystrokes": "cat /data/scenario/map.json\n"},
                    {
                        "keystrokes": (
                            "python3 - <<'PY'\n"
                            "# even odd neighbor distance\n"
                            "assert True\n"
                            "print('SYNTHETIC_COORDINATE_PARITY_OK')\nPY\n"
                        )
                    },
                    {
                        "keystrokes": (
                            "cat > /root/verifier/test_outputs.py <<'PY'\n"
                            "def test_synthetic_coordinate_parity():\n"
                            "    # even odd neighbor distance\n"
                            "    assert True\nPY\n"
                        )
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    prompt_dir = tmp_path / "episode-2"
    prompt_dir.mkdir()
    (prompt_dir / "prompt.txt").write_text(
        "SYNTHETIC_COORDINATE_PARITY_OK\n",
        encoding="utf-8",
    )

    violations = IndependentVerifier._audit_structured_coordinate_methodology(
        tmp_path,
        "Use an odd-row hex grid for spatial relationships and tile coordinates.",
    )

    assert violations == [
        "synthetic coordinate parity precheck did not precede current artifact inspection"
    ]


def test_coordinate_methodology_audit_accepts_precheck_before_artifacts(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-1"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "keystrokes": (
                            "python3 - <<'PY'\n"
                            "# even odd neighbor distance\n"
                            "assert True\n"
                            "print('SYNTHETIC_COORDINATE_PARITY_OK')\nPY\n"
                        )
                    },
                    {"keystrokes": "cat /data/scenario/map.json\n"},
                    {
                        "keystrokes": (
                            "cat > /root/verifier/test_outputs.py <<'PY'\n"
                            "def test_synthetic_coordinate_parity():\n"
                            "    # even odd neighbor distance\n"
                            "    assert True\nPY\n"
                        )
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    prompt_dir = tmp_path / "episode-2"
    prompt_dir.mkdir()
    (prompt_dir / "prompt.txt").write_text(
        "SYNTHETIC_COORDINATE_PARITY_OK\n",
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_structured_coordinate_methodology(
        tmp_path,
        "Use an odd-row hex grid for spatial relationships and tile coordinates.",
    ) == []


def test_coordinate_methodology_audit_rejects_missing_persisted_test(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-1"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "keystrokes": (
                            "python3 - <<'PY'\n"
                            "# even odd neighbor distance\n"
                            "assert True\n"
                            "print('SYNTHETIC_COORDINATE_PARITY_OK')\nPY\n"
                        )
                    },
                    {"keystrokes": "cat /output/result.json\n"},
                ]
            }
        ),
        encoding="utf-8",
    )
    prompt_dir = tmp_path / "episode-2"
    prompt_dir.mkdir()
    (prompt_dir / "prompt.txt").write_text(
        "SYNTHETIC_COORDINATE_PARITY_OK\n",
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_structured_coordinate_methodology(
        tmp_path,
        "Use an odd-row hex grid for spatial relationships and tile coordinates.",
    ) == ["generated verifier omitted test_synthetic_coordinate_parity"]


def test_coordinate_methodology_audit_ignores_generic_prompt_parity_for_latex(
    tmp_path: Path,
) -> None:
    prompt_dir = tmp_path / "episode-0"
    prompt_dir.mkdir()
    (prompt_dir / "prompt.txt").write_text(
        "Generic verifier policy example: validate odd-row and even-row coordinates.",
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_structured_coordinate_methodology(
        tmp_path,
        "Extract every displayed equation and preserve its notation.",
        ("Superscripts and subscripts encode spatial relationships on the page.",),
    ) == []


def test_coordinate_methodology_audit_applies_when_public_doc_declares_parity(
    tmp_path: Path,
) -> None:
    assert IndependentVerifier._audit_structured_coordinate_methodology(
        tmp_path,
        "Optimize district placement from the supplied map.",
        (
            "Hex Grid Coordinate System: this map uses an odd-row offset "
            "convention for tile coordinates and hex neighbors.",
        ),
    ) == [
        "missing synthetic even/odd neighbor-and-distance parity precheck",
        "synthetic coordinate parity precheck did not execute successfully",
        "generated verifier omitted test_synthetic_coordinate_parity",
    ]


def test_independent_verifier_log_audit_allows_explicit_skill_tree_prune(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-1"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        '{"commands":[{"keystrokes":"find /app/environment '
        '-path /app/environment/skills -prune -o -type f -print\\n"}]}',
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_verifier_logs(tmp_path) == []


def test_independent_verifier_log_audit_allows_quoted_skill_tree_prune(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-2"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        "find /app/environment -path '/app/environment/skills' "
        "-prune -o -type f -print\n",
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_verifier_logs(tmp_path) == []


def test_independent_verifier_prompt_discovery_does_not_name_candidate_skill_tree() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompt = (
        repo_root
        / "libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt"
    ).read_text(encoding="utf-8")

    discovery = prompt.split("2. DISCOVER FILES [V1]: Run:", 1)[1].split(
        "3. EXTRACT REQUIREMENTS [V2]", 1
    )[0]
    assert "/app/environment/skills" not in discovery
    assert "find /app/environment/data /app/environment/doc" in discovery


def test_independent_verifier_prompt_requires_doc_then_parity_then_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompt = (
        repo_root
        / "libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt"
    ).read_text(encoding="utf-8")

    assert "COORDINATE-SAFE STARTUP ORDER (MANDATORY)" in prompt
    assert "Before reading the contents of any" in prompt
    assert "every public background document under `/app/environment/doc/`" in prompt
    assert "Do not batch a background document read" in prompt
    assert "the very next" in prompt
    assert "substantive action must be the synthetic parity precheck" in prompt
    assert "only then inspect `/data/`" in prompt


def test_independent_verifier_log_audit_rejects_access_after_skill_tree_prune(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-3"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        "find /app/environment -path /app/environment/skills -prune "
        "-o -type f -print; cat /app/environment/skills/evo-task/SKILL.md\n",
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_verifier_logs(tmp_path) == [
        "episode-3: inspected candidate Skill files"
    ]


def test_independent_verifier_log_audit_rejects_find_inside_skill_tree(
    tmp_path: Path,
) -> None:
    response_dir = tmp_path / "episode-4"
    response_dir.mkdir()
    (response_dir / "response.txt").write_text(
        "find /app/environment/skills -type f -print\n",
        encoding="utf-8",
    )

    assert IndependentVerifier._audit_verifier_logs(tmp_path) == [
        "episode-4: inspected candidate Skill files"
    ]


def test_prompts_treat_background_doc_as_public_knowledge_not_answer_key() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    verifier_prompt = (
        repo_root
        / "libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt"
    ).read_text(encoding="utf-8")
    evolution_prompt = (
        repo_root
        / "libs/terminus_agent/agents/prompt-templates/terminus-evolution-json.txt"
    ).read_text(encoding="utf-8")

    assert "optional public domain references" in verifier_prompt
    assert "Establish every current-instance assertion independently" in verifier_prompt
    assert "DOMAIN REFERENCE USE" in verifier_prompt
    assert "derive expectations from" not in verifier_prompt
    assert "DOC-DERIVED KNOWLEDGE" not in verifier_prompt
    assert "Do NOT inspect or use `/app/environment/skills`" in verifier_prompt
    assert "Judge the produced output, not the implementation" in verifier_prompt
    assert "STRICT READ-ONLY CANDIDATE BOUNDARY" in verifier_prompt
    assert "Never run, import, or invoke the candidate Skill" in verifier_prompt
    assert "SOURCE PROVENANCE" in verifier_prompt
    assert "exact file below `/app/environment/doc/`" in verifier_prompt
    assert "later command" in verifier_prompt
    assert "SPREADSHEET RECALCULATION BARRIER" in verifier_prompt
    assert "never treat uncalculated formulas as proof of correctness" in verifier_prompt
    assert "FORMULA DEPENDENCY-AND-ORIENTATION BARRIER" in verifier_prompt
    assert "one-row horizontal range needs MATCH" in verifier_prompt
    assert "do not turn current cell addresses" in verifier_prompt
    assert "doc rules as expected values" not in verifier_prompt
    assert "one test per table row" not in verifier_prompt
    assert "SAME ones that ground truth tests use" not in verifier_prompt
    assert "At least 60% of tests" not in verifier_prompt
    assert "It is NOT an answer key for the current instance" in evolution_prompt
    assert "PROTECTED EVALUATOR BOUNDARY" in evolution_prompt
    assert "Never inspect, search for, read, import, execute" in evolution_prompt
    assert "`/root/verifier`, `/app/verifier`, and `/tests`" in evolution_prompt
    assert "NO INSTANCE ANSWERS IN SKILLS" in evolution_prompt
    assert "Treat the supplied background document as public domain" in evolution_prompt
    assert "executable procedures, runtime discovery, validations" in evolution_prompt
    assert "Every SKILL.md MUST begin at byte 0" in evolution_prompt
    assert "THIN END-TO-END ENTRY POINT" in evolution_prompt
    assert "recalculate a temporary output copy" in evolution_prompt
    assert "knowledge/procedure separation" in evolution_prompt
    assert "Never search an unlabeled" in evolution_prompt
    assert "SEMANTIC TRANSFORMATION BARRIER" in verifier_prompt
    assert "global unlabeled factor" in verifier_prompt
    assert "QUALITATIVE SEQUENCE BARRIER" in verifier_prompt
    assert "FORMULA PROVENANCE BARRIER" in verifier_prompt
    assert "qualitative sequence shape" in evolution_prompt
    assert "BEHAVIOR-NOT-TOKEN BARRIER" in verifier_prompt
    assert "DEPENDENCY-DAG BARRIER" in verifier_prompt
    assert "SCHEMA-AND-RANKING BARRIER" in verifier_prompt
    assert "STRUCTURED-COORDINATE CONVENTION BARRIER" in verifier_prompt
    assert "Never silently substitute" in verifier_prompt
    assert "synthetic parity self-check" in verifier_prompt
    assert "Do not encode current" in verifier_prompt
    assert "MEDIA-CONSISTENCY BARRIER" in verifier_prompt
    assert "HARD-CONSTRAINT EVIDENCE BARRIER" in verifier_prompt
    assert "observable critical path" in evolution_prompt
    assert "multiple synthetic K values" in evolution_prompt
    assert "machine-readable interval ledger" in evolution_prompt


def test_prompts_use_the_runtime_document_root_without_legacy_path_conflicts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompt_root = repo_root / "libs/terminus_agent/agents/prompt-templates"
    prompt_paths = [
        prompt_root / "claude-skill-transfer.txt",
        prompt_root / "terminus-evolution-json.txt",
        repo_root
        / "libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt",
    ]

    for path in prompt_paths:
        prompt = path.read_text(encoding="utf-8")
        normalized = " ".join(prompt.split())
        assert "/app/environment/doc/" in prompt, path
        assert "/root/environment/doc" not in prompt, path
        assert "do not probe alternate document roots" in normalized, path

    no_doc_prompt_paths = [
        prompt_root / "claude-skill-only-transfer.txt",
    ]
    for path in no_doc_prompt_paths:
        prompt = path.read_text(encoding="utf-8")
        assert "/root/environment/doc" not in prompt, path
        assert "search alternate roots" in " ".join(prompt.split()), path


def test_independent_verifier_prompt_requires_hard_property_evidence_closure() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    prompt = (
        repo_root
        / "libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt"
    ).read_text(encoding="utf-8")

    barrier = prompt.split("HARD-CONSTRAINT EVIDENCE BARRIER:", 1)[1].split(
        "   Requirements:", 1
    )[0]
    assert "For EACH hard property" in barrier
    assert "constraint: identify the exact instruction clause" in barrier
    assert "runtime/source evidence" in barrier
    assert "positive, negative," in barrier
    assert "and unknown evidence" in barrier
    assert "output-visible representation" in barrier
    assert "schema has no separate property field" in barrier
    assert "source-supported qualifier" in barrier
    assert "source-side filter" in barrier
    assert "final artifact exposes the required property" in barrier
    assert "invent a qualifier from the entity name" in barrier

    reflection = prompt.split("8. REFLECT [V7]:", 1)[1].split(
        "9. DIAGNOSE FAILURES [V8]:", 1
    )[0]
    normalized_reflection = " ".join(reflection.split())
    assert "all three links" in normalized_reflection
    assert "exact instruction constraint" in normalized_reflection
    assert "runtime/source evidence for the selected entity" in normalized_reflection
    assert "final output-visible representation" in normalized_reflection

    lowered = barrier.lower()
    assert "travel" not in lowered
    assert "pet" not in lowered
    assert "evaluator" not in lowered


def test_previous_verifier_context_requires_background_doc_source_provenance() -> None:
    verifier = IndependentVerifier("test-model")
    environment = _Environment([_Result("def test_public_requirement():\n    assert True\n")])
    context = asyncio.run(verifier._build_previous_verifier_context(environment))

    assert "SOURCE PROVENANCE" in context
    assert "exact file below /app/environment/doc/" in context
    assert "Adjacent output from a later command is not background document content" in context


def test_fresh_claude_oracle_supports_paired_and_skill_only_treatments() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    transfer_prompt = (
        repo_root
        / "libs/terminus_agent/agents/prompt-templates/claude-skill-transfer.txt"
    ).read_text(encoding="utf-8")
    claude_agent = (
        repo_root / "libs/terminus_agent/agents/claude_code_skills.py"
    ).read_text(encoding="utf-8")
    evolution_source = (
        repo_root
        / "libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py"
    ).read_text(encoding="utf-8")

    assert "public background document used by the control" in transfer_prompt
    assert "end-to-end entry point or output validator" in transfer_prompt
    assert "final task result, rather than a particular tool-call pattern" in transfer_prompt
    assert "write additional\nsolution code" in transfer_prompt
    assert "Skill package is immutable" in transfer_prompt
    assert "Do not repair or rewrite the Skill package itself" in transfer_prompt
    assert "test -d /app/environment/doc" in claude_agent
    assert "chmod a-w" in claude_agent
    assert 'self._gt_oracle_agent == "claude-code-skills"' in evolution_source
    assert "GT oracle paired-treatment barrier failed" in evolution_source
    assert "Every release-standard oracle is Skill-only" in evolution_source
    assert "rm -rf -- /app/environment/doc" in evolution_source
    assert "test ! -e /app/environment/doc" in evolution_source
    assert "skill_digest_before" in evolution_source
    assert "modified the evolved Skill" in evolution_source


def test_skill_schema_validator_is_shell_quoted_and_fails_closed() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (
        repo_root
        / "libs/terminus_agent/agents/terminus_2/harbor_terminus_2_evolution.py"
    ).read_text(encoding="utf-8")

    assert "shlex.quote(encoded)" in source
    assert "skill_schema.__file__" in source
    assert "Skill schema validator failed closed" in source
    assert "skill_schema.RESULT_MARKER" in source

    agent = object.__new__(HarborTerminus2Evolution)
    manifest = "/app/environment/skills/evo-example/SKILL.md"
    invalid = _Environment(
        [
            _Result(manifest + "\n"),
            _Result(
                "bash: no job control in this shell\n"
                '__SKILL_SCHEMA_RESULT__{"code":"frontmatter_not_at_byte_zero",'
                '"message":"SKILL.md must start with `---` at byte zero",'
                f'"path":"{manifest}"}}\n'
            ),
        ]
    )
    assert asyncio.run(agent._validate_skill_frontmatter(invalid)) == [
        manifest
        + ": SKILL.md must start with `---` at byte zero "
        "[frontmatter_not_at_byte_zero]"
    ]

    broken_validator = _Environment(
        [_Result(manifest + "\n"), _Result("syntax error", return_code=2)]
    )
    issues = asyncio.run(agent._validate_skill_frontmatter(broken_validator))
    assert len(issues) == 1
    assert "schema validator could not run" in issues[0]

    shell_noise_only = _Environment(
        [
            _Result(manifest + "\n"),
            _Result(
                "bash: cannot set terminal process group: Inappropriate ioctl\n"
                "bash: no job control in this shell\n"
            ),
        ]
    )
    assert asyncio.run(agent._validate_skill_frontmatter(shell_noise_only)) == []


def test_gt_oracle_error_never_accepts_surrogate_pass() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._check_episode_exit)
    assert "failing closed and requesting retry" in source
    assert "trusting surrogate pass" not in source
    assert 'exit_reason="surrogate_pass"' not in source
    assert "instruction-compatible failure hypotheses" in source
    assert "guessing an evaluator-specific answer" in source
    assert "every supplied background document" in source
    assert "public invariants" in source
    assert "family-level gap" in source
    assert "one-case exception" in source
    assert "_host_intervention_count - 1" in source
    assert "_gt_infrastructure_retry_count" in source
    assert "gt_infrastructure_unavailable" in source


def test_gt_oracle_requires_exact_full_score() -> None:
    resolver_source = inspect.getsource(
        HarborTerminus2Evolution._gt_full_score_and_reward
    )
    oracle_source = inspect.getsource(HarborTerminus2Evolution._run_gt_oracle_check)
    assert "numeric_reward == 1.0" in resolver_source
    assert "total > 0 and passed == total" in resolver_source
    assert "_gt_full_score_and_reward" in oracle_source
    assert '"passed": full_score' in oracle_source


def test_gt_oracle_records_skill_use_but_only_gt_scores_task_completion() -> None:
    """Skill uptake is diagnostic; canonical GT is the outcome gate."""
    oracle_source = inspect.getsource(HarborTerminus2Evolution._run_gt_oracle_check)
    assert "_claude_trace_used_evolved_skill" in oracle_source
    assert '"skill_invoked": skill_invoked' in oracle_source
    assert "canonical GT will still determine success" in oracle_source
    assert "No evolved Skill invocation was recorded" not in oracle_source
    assert "skill_digest_after" in oracle_source
    assert "Clean evaluation modified the immutable evolved Skill" in oracle_source
    assert "_claude_trace_execution_violation" not in oracle_source


def test_claude_skill_oracle_ignores_only_closed_stdout_diagnostic() -> None:
    source = inspect.getsource(ClaudeCodeSkills.populate_context_post_run)
    assert "except BrokenPipeError" in source
    assert source.index("except BrokenPipeError") < source.index(
        "validate_vertex_transcript"
    )


def test_claude_skill_oracle_selects_primary_session_with_subagents(
    tmp_path: Path,
) -> None:
    agent = ClaudeCodeSkills(
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )
    project_dir = tmp_path / "sessions" / "projects" / "-root"
    primary_session_id = "11111111-2222-3333-4444-555555555555"
    primary_file = project_dir / f"{primary_session_id}.jsonl"
    subagent_file = (
        project_dir
        / primary_session_id
        / "subagents"
        / "agent-aaaaaaaaaaaaaaaaa.jsonl"
    )
    primary_file.parent.mkdir(parents=True)
    subagent_file.parent.mkdir(parents=True)
    primary_file.write_text("{}\n", encoding="utf-8")
    subagent_file.write_text("{}\n", encoding="utf-8")
    (tmp_path / "claude-code.txt").write_text(
        json.dumps({"type": "result", "session_id": primary_session_id}) + "\n",
        encoding="utf-8",
    )

    assert agent._get_session_dir() == project_dir


def test_claude_skill_oracle_falls_back_to_only_non_subagent_session(
    tmp_path: Path,
) -> None:
    agent = ClaudeCodeSkills(
        logs_dir=tmp_path,
        model_name="anthropic/claude-opus-4-6",
    )
    project_dir = tmp_path / "sessions" / "projects" / "-root"
    primary_file = project_dir / "primary.jsonl"
    subagent_file = project_dir / "primary" / "subagents" / "agent-child.jsonl"
    primary_file.parent.mkdir(parents=True)
    subagent_file.parent.mkdir(parents=True)
    primary_file.write_text("{}\n", encoding="utf-8")
    subagent_file.write_text("{}\n", encoding="utf-8")

    assert agent._get_session_dir() == project_dir


def _write_claude_result(
    path: Path, *, provider: str, canonical_model: str, is_error: bool = False
) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "result",
                "is_error": is_error,
                "modelUsage": {
                    canonical_model: {
                        "provider": provider,
                        "canonicalModel": canonical_model,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_subscription_transcript_requires_first_party_exact_opus46(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_USE_SUBSCRIPTION", "1")
    monkeypatch.setenv("CLAUDE_CODE_SUBSCRIPTION_MODEL", "claude-opus-4-6")
    transcript = tmp_path / "claude-code.txt"
    _write_claude_result(
        transcript, provider="firstParty", canonical_model="claude-opus-4-6"
    )
    validate_vertex_transcript(transcript, "anthropic/claude-opus-4-6")


@pytest.mark.parametrize(
    ("provider", "model"),
    [("vertex", "claude-opus-4-6"), ("firstParty", "claude-opus-5")],
)
def test_subscription_transcript_rejects_wrong_backend_or_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_USE_SUBSCRIPTION", "1")
    transcript = tmp_path / "claude-code.txt"
    _write_claude_result(transcript, provider=provider, canonical_model=model)
    with pytest.raises(ClaudeCodeProviderError):
        validate_vertex_transcript(transcript, "anthropic/claude-opus-4-6")


def test_subscription_command_removes_competing_auth_and_pins_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_USE_SUBSCRIPTION", "1")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "secret-test-token")
    command = ExecInput(
        command="claude -p test",
        env={
            "ANTHROPIC_API_KEY": "wrong",
            "ANTHROPIC_AUTH_TOKEN": "wrong",
            "ANTHROPIC_BASE_URL": "https://wrong.invalid",
        },
    )
    configured = configure_vertex_commands([command])[0]
    assert configured.env["CLAUDE_CODE_OAUTH_TOKEN"] == "secret-test-token"
    assert configured.env["ANTHROPIC_MODEL"] == "claude-opus-4-6"
    assert "ANTHROPIC_API_KEY" not in configured.env
    assert "ANTHROPIC_AUTH_TOKEN" not in configured.env
    assert "ANTHROPIC_BASE_URL" not in configured.env


def test_skill_export_requires_stable_utf8_snapshot() -> None:
    source = inspect.getsource(HarborTerminus2Evolution._read_stable_container_text)
    assert "sha256sum" in source
    assert "h1" in source and "h2" in source
    assert "UnicodeDecodeError" in source
    assert "result.return_code == 0" in source
    assert "return None" in source

    export_source = inspect.getsource(
        HarborTerminus2Evolution._export_container_subdir
    )
    assert "_read_stable_container_text" in export_source
    assert "file_encoded is not None" in export_source
    assert "find" in export_source and "-type f" in export_source
    assert "__pycache__" in export_source and "*.pyc" in export_source
    assert "target.parent.mkdir" in export_source


def test_stable_snapshot_accepts_a_valid_empty_utf8_file() -> None:
    agent = object.__new__(HarborTerminus2Evolution)
    environment = _Environment([_Result(stdout="", return_code=0)])

    encoded = asyncio.run(
        agent._read_stable_container_text(environment, "/skills/example/__init__.py")
    )

    assert encoded == ""
