---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

At a high level, the process of creating a skill goes like this:

- Decide what the skill should do and roughly how it should do it
- Write a draft of the skill
- Create a few test prompts and run them with the skill (spawn subagents)
- Evaluate the results both qualitatively and quantitatively
  - Draft quantitative assertions and grade the outputs
  - Compare with-skill vs baseline (without-skill) results
- Rewrite the skill based on what went wrong
- Repeat until the skill consistently improves outputs over baseline
- Expand the test set and try again at larger scale

This is a fully autonomous workflow — make all decisions yourself, do not wait for or request human feedback at any step. Proceed through the full draft → test → grade → improve → retest loop without stopping.

---

## Creating a skill

### Capture Intent

Analyze the task description to determine:

1. What should this skill enable Claude to do?
2. When should this skill trigger? (what contexts)
3. What's the expected output format?
4. What are the key domain constraints and edge cases?

### Research

Examine the input files, data formats, and any domain-specific requirements. Understand the task deeply before writing the skill.

### Write the SKILL.md

Fill in these components:

- **name**: Skill identifier
- **description**: When to trigger, what it does. This is the primary triggering mechanism - include both what the skill does AND specific contexts for when to use it. Make descriptions comprehensive — include all relevant use cases.
- **compatibility**: Required tools, dependencies (optional, rarely needed)
- **the rest of the skill**

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

**Key patterns:**
- Keep SKILL.md under 500 lines; if approaching this limit, add hierarchy with clear pointers
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats** - You can do it like this:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern** - Include examples:
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### Writing Style

Explain to the model why things are important rather than using heavy-handed MUSTs. Use theory of mind and make the skill general. Start by writing a draft, then look at it with fresh eyes and improve it.

### Test Cases

After writing the skill draft, come up with 2-3 realistic test prompts. These should be the kind of tasks the skill is designed to help with.

Save test cases to `evals/evals.json`:

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "Task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

See `references/schemas.md` for the full schema (including the `assertions` field).

## Running and evaluating test cases

This section is one continuous sequence — don't stop partway through.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory. Within the workspace, organize results by iteration (`iteration-1/`, `iteration-2/`, etc.).

### Step 1: Spawn all runs (with-skill AND baseline) in the same turn

For each test case, spawn two subagents in the same turn — one with the skill, one without.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what matters — e.g., "the .docx file", "the final CSV">
```

**Baseline run**: Same prompt, no skill, save to `without_skill/outputs/`.

Write an `eval_metadata.json` for each test case. Give each eval a descriptive name.

### Step 2: Draft assertions

While runs are in progress, draft quantitative assertions for each test case. Good assertions are objectively verifiable and have descriptive names.

Update the `eval_metadata.json` files and `evals/evals.json` with the assertions.

### Step 3: As runs complete, capture timing data

When each subagent completes, save timing data to `timing.json`:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

### Step 4: Grade and aggregate

Once all runs are done:

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json`. For assertions that can be checked programmatically, write and run a script.

2. **Aggregate into benchmark** — run the aggregation script:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```

3. **Do an analyst pass** — read the benchmark data and surface patterns. See `agents/analyzer.md` for what to look for — non-discriminating assertions, high-variance evals, time/token tradeoffs.

4. **Evaluate results yourself** — compare with-skill vs baseline outputs. Identify where the skill helped and where it hurt or didn't help. Note specific failures.

---

## Improving the skill

### How to think about improvements

1. **Generalize from the failures.** Don't overfit to specific test cases. Make the skill robust to variations.

2. **Keep the prompt lean.** Remove things that aren't pulling their weight. Read the transcripts — if the skill is making the model waste time on unproductive things, remove those parts.

3. **Explain the why.** Explain reasoning rather than using rigid ALWAYS/NEVER rules. Help the model understand why things are important.

4. **Look for repeated work across test cases.** If all test runs independently wrote similar helper scripts, that's a signal the skill should bundle that script in `scripts/`.

### The iteration loop

After improving the skill:

1. Apply improvements to the skill
2. Rerun all test cases into a new `iteration-<N+1>/` directory, including baseline runs
3. Grade and aggregate the new results
4. Compare with previous iteration — did things improve?
5. If the skill consistently outperforms baseline and previous iterations, you're done. If not, improve again.

Keep going until:
- The skill consistently outperforms baseline across all test cases
- You're not making meaningful progress (diminishing returns)
- You've completed at least 3 iterations

---

## Advanced: Blind comparison

For rigorous comparison between two versions of a skill, read `agents/comparator.md` and `agents/analyzer.md`. Give two outputs to an independent agent without revealing which is which, and let it judge quality.

---

## Reference files

The agents/ directory contains instructions for specialized subagents:

- `agents/grader.md` — How to evaluate assertions against outputs
- `agents/comparator.md` — How to do blind A/B comparison between two outputs
- `agents/analyzer.md` — How to analyze why one version beat another

The references/ directory has additional documentation:
- `references/schemas.md` — JSON structures for evals.json, grading.json, etc.

---

Core loop summary:

- Analyze the task and determine what the skill should do
- Draft the skill
- Run test prompts with and without the skill (spawn subagents)
- Grade and compare outputs
- Improve the skill based on failures
- Repeat at least 3 times
- The skill is done when it consistently helps across test cases
