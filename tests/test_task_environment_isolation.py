import runpy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS = REPO_ROOT / "tasks"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_jax_reference_outputs_are_verifier_computed() -> None:
    task = TASKS / "jax-computing-basics"
    environment = task / "environment"
    dockerfile = _read(environment / "Dockerfile")
    verifier = _read(task / "tests" / "test_outputs.py")

    assert not (environment / "reference").exists()
    assert "COPY reference" not in dockerfile
    assert "reference/" in _read(environment / ".dockerignore")
    assert "/app/reference" not in verifier
    assert "def compute_expected" in verifier
    assert 'VERIFIER_PROBLEM_FILE = Path("/tests/problem.json")' in verifier
    assert 'VERIFIER_DATA_DIR = Path("/tests/data")' in verifier
    assert "/app/problem.json" not in verifier
    assert "/app/data" not in verifier
    assert "EXPECTED_TASKS =" in verifier

    verifier_inputs = task / "tests"
    assert (verifier_inputs / "problem.json").is_file()
    assert {
        path.name for path in (verifier_inputs / "data").iterdir() if path.is_file()
    } == {"x.npy", "logistic.npz", "seq.npz", "mlp.npz"}

    solution = _read(task / "solution" / "solve.sh")
    assert "import jax_skills" not in solution
    assert "np.save(root / task[\"output\"]" in solution


def test_quantum_reference_is_created_only_by_the_verifier() -> None:
    task = TASKS / "quantum-numerical-simulation"
    environment = task / "environment"
    dockerfile = _read(environment / "Dockerfile")
    verifier = _read(task / "tests" / "test_outputs.py")

    assert not (environment / "precompute_reference.py").exists()
    assert "/opt/reference" not in dockerfile
    assert "precompute_reference" not in dockerfile
    assert "/opt/reference" not in verifier
    assert "return _compute_reference_wigners()" in verifier


def test_hvac_hidden_plant_is_confined_to_a_sidecar() -> None:
    task = TASKS / "hvac-control"
    environment = task / "environment"
    main_dockerfile = _read(environment / "Dockerfile")
    sidecar_dockerfile = _read(environment / "Dockerfile.simulator")
    compose = _read(environment / "docker-compose.yaml")
    client = _read(environment / "hvac_simulator.py")

    assert not (environment / "verification_params.json").exists()
    assert (task / "tests" / "verification_params.json").is_file()
    assert "hvac_service.py" not in main_dockerfile
    assert "COPY hvac_service.py" in sidecar_dockerfile
    assert "HVAC_SIMULATOR_URL=http://simulator:8080" in compose
    assert "docker.sock" not in compose
    for provider_variable in (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CLAUDE_CODE_USE_VERTEX",
        "CLOUD_ML_REGION",
        "ANTHROPIC_VERTEX_PROJECT_ID",
    ):
        assert provider_variable not in compose
    assert "PROCESS_GAIN" not in client
    assert "TIME_CONSTANT" not in client
    assert "0.12" not in client
    assert "40.0" not in client


def test_python_scala_reference_material_is_verifier_only() -> None:
    task = TASKS / "python-scala-translation"
    environment = task / "environment"
    dockerfile = _read(environment / "Dockerfile")

    assert not (environment / "localtest").exists()
    assert not list(environment.glob("**/Tokenizer.scala"))
    assert not (environment / "convert_tokenizer.py").exists()
    assert "COPY localtest" not in dockerfile
    assert "TokenizerSpec.scala" not in dockerfile
    assert "must declare `package tokenizer`" in _read(task / "instruction.md")

    dockerignore = _read(environment / ".dockerignore")
    assert "localtest/" in dockerignore
    assert "scala_tokenizer/src/" in dockerignore

    assert (task / "tests" / "TokenizerSpec.scala").is_file()
    assert (task / "tests" / "build.sbt").is_file()
    test_script = _read(task / "tests" / "test.sh")
    assert "rm -rf -- /root/localtest" in test_script
    assert "/tests/TokenizerSpec.scala" in test_script
    assert "/tests/build.sbt" in test_script
    assert "/root/build.sbt" not in test_script
    assert "mkdir -p /root/localtest/project" in test_script


def test_agentops_passing_artifact_is_removed_with_a_final_canary() -> None:
    environment = TASKS / "fix-build-agentops" / "environment"
    dockerfile = _read(environment / "Dockerfile")
    checker = _read(environment / "assert_isolation.sh")
    verifier_script = _read(TASKS / "fix-build-agentops" / "tests" / "test.sh")

    assert "rm -rf /home/github/build/passed" in dockerfile
    assert "rm -rf /home/github/24653510459" in dockerfile
    assert "rm -f /usr/local/bin/run_passed.sh" in dockerfile
    assert "-name '*-orig.log' -delete" in dockerfile
    assert "test ! -e /home/github/build/passed" in dockerfile
    assert "rm -rf \"$repo/.git\"" in dockerfile
    assert "git -C \"$repo\" init -q -b main" in dockerfile
    assert "mv \"$action_src\" /home/github/ci-runtime" in dockerfile
    assert "GITHUB_SHA=$TASK_SOURCE_SHA" in dockerfile
    assert "s/fix-crash-endtimestamp/task-baseline/g" in dockerfile
    assert "COPY assert_isolation.sh /usr/local/bin/assert-agentops-isolation" in dockerfile
    assert "/usr/local/bin/assert-agentops-isolation --initial" in dockerfile

    assert "rev-list --max-parents=0 --all" in checker
    assert "rev-list --all --count" in checker
    assert "numeric BugSwarm run directory is present" in checker
    assert "GITHUB_SHA=[0-9a-f]{40}" in checker
    assert '"(id|tree_id)"' in checker
    assert "ddf27539541861da67ccdb629ae68bd39bff9ee7" not in checker
    assert "24579293289" not in checker
    assert "24653510459" not in checker
    assert "33e45e7e29832034dca82f4e87c0509b3575246e" not in checker
    assert "objects/info/alternates" in checker
    assert "fsck --full --unreachable --no-reflogs" in checker
    assert "/usr/local/bin/assert-agentops-isolation --lineage" in verifier_script
    assert "ln -s /home/github/ci-runtime /home/github/24653510459" in verifier_script

    dockerignore = _read(environment / ".dockerignore")
    assert "!doc/**" in dockerignore
    assert "!skills/**" in dockerignore


def test_druid_source_has_no_future_git_history() -> None:
    environment = TASKS / "fix-druid-loophole-cve" / "environment"
    dockerfile = _read(environment / "Dockerfile")

    assert "git clone --depth 1 --single-branch --branch druid-0.20.0" in dockerfile
    assert "acdc6ee7ea3a81fb3e70b92d7cc682921f988eb5" in dockerfile
    assert 'rev-list --count HEAD)\" = \"1\"' in dockerfile
    assert "git remote remove origin" in dockerfile
    assert 'rev-list --all --count)\" = \"1\"' in dockerfile
    assert 'test -z \"$(git remote)\"' in dockerfile
    assert "refs/tags refs/remotes" in dockerfile

    verifier = _read(TASKS / "fix-druid-loophole-cve" / "tests" / "test_outputs.py")
    assert '["git", "diff", "--name-only"]' in verifier
    assert "_assert_successful_sample" in verifier
    assert "response.status_code == 200" in verifier
    assert 'payload.get("numRowsRead") == 1' in verifier
    assert "_assert_explicit_exploit_rejection" in verifier
    assert "Generic service failures are not evidence of a security fix" in verifier
    assert '"javascript is disabled"' in verifier

    dockerignore = _read(environment / ".dockerignore")
    assert "!doc/**" in dockerignore
    assert "!skills/**" in dockerignore


def test_druid_verifier_rejects_a_generic_server_failure() -> None:
    verifier_path = TASKS / "fix-druid-loophole-cve" / "tests" / "test_outputs.py"
    namespace = runpy.run_path(str(verifier_path))
    assert_rejected = namespace["_assert_explicit_exploit_rejection"]

    class Response:
        def __init__(self, status_code: int, text: str):
            self.status_code = status_code
            self.text = text

        @staticmethod
        def json():
            raise ValueError("not JSON")

    payload = {"name": "negative-control", "rce_indicator": None}
    with pytest.raises(AssertionError, match="failed only generically"):
        assert_rejected(Response(500, "Internal Server Error"), payload)

    assert_rejected(
        Response(500, "JavaScript is disabled for security reasons"),
        payload,
    )
