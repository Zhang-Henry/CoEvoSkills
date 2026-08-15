# CoEvoSkills agent implementation

This package adapts Harbor's Terminus-2 agent and adds:

- dynamic skill discovery and loading;
- a skill-generation execution mode;
- an independently instantiated surrogate verifier;
- verifier test refinement after ground-truth disagreement;
- fresh-container ground-truth oracle execution;
- persisted skill and verifier artifacts;
- experiment summaries used by `run_exp.py`.

Additional native Harbor Agents can be registered without editing the built-in
registry by passing
`--agent-import-path NAME=python.module:AgentClass` through `run_exp.py` or
`scripts/run_condition.sh`. The same registered name may be selected as the
fresh ground-truth Agent.

## Main entry points

- `agents/terminus_2/harbor_terminus_2_evolution.py` — CoEvoSkills loop.
- `agents/terminus_2/harbor_terminus_2_skills.py` — fresh agent with
  pre-installed skills.
- `evolution/independent_verifier.py` — independent verifier session.
- `evolution/self_verifier.py` — executes and parses generated checks.
- `evolution/prompt_templates/` — verifier prompts.
- `agents/prompt-templates/terminus-evolution-json.txt` — generator prompt.

The evolution agent injects `meta_skills/skill-creator/` from the repository
root. The legacy `.claude/skills/` location remains a compatibility fallback.
Provider credentials are read from the process environment and are never stored
in this package.

This implementation is derived from SkillsBench and Harbor/Terminus-2. See the
root `NOTICE` and `LICENSE` files.
