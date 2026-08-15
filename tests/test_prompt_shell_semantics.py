from pathlib import Path

PROMPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "libs"
    / "terminus_agent"
    / "agents"
    / "prompt-templates"
)


def test_all_command_prompts_explain_non_persistent_shells() -> None:
    prompt_names = (
        "terminus-evolution-json.txt",
        "terminus-json-plain.txt",
        "terminus-xml-plain.txt",
    )

    for prompt_name in prompt_names:
        prompt = (PROMPT_DIR / prompt_name).read_text(encoding="utf-8")
        assert "fresh, non-persistent shell" in prompt
        assert "cd /absolute/project && make test" in prompt
