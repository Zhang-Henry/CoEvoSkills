# Release bundle

This directory is an immutable input to public reproduction commands. Runtime
code reads from it but never writes generated Skills or logs back into it.

`background_docs/` contains one audited, answer-free background document set
for each of the 85 benchmark tasks.

`skills/` contains one Agent-generated, schema-valid Skill package for every
task. The Skill-only condition never exposes the corresponding background
document to the evaluation Agent.

`skill_status.tsv` distinguishes Skills that obtained canonical reward `1.0`
in a fresh Skill-only evaluation from retained candidates that did not satisfy
the finalization gate. Candidate artifacts are included so every evolution
attempt can be inspected and rerun; they are not reported as successful tasks.
The current manifest contains 62 validated Skills (62/85, or 72.9%) and 23
candidate Skills.

`evaluations/release-skill-only-results.tsv` is the sole public result table.
It contains exactly one row for each currently validated Skill. Every row
records canonical reward `1.0` from a fresh Claude Code Opus 4.6 Skill-only
evaluation, confirms that no background document was available, and pins the
current release Skill and background-document trees by SHA-256. Candidate
statuses remain available in `skill_status.tsv` but are not included in the
result table. The test counts distinguish passed checks from checks skipped as
inapplicable; no finalized row contains a failed check. Raw Agent conversations
and Docker task sandboxes are not release artifacts.

During a run, `scripts/prepare_tasks.py` copies the selected release material
to `workspaces/<RUN_ID>/<condition>/`. Evolution may modify that workspace. A
run-specific snapshot is then stored under `outputs/<RUN_ID>/`; neither
location is a source of truth for this release bundle.

Alternative release versions can use the same layout in another directory and
be selected with `scripts/prepare_tasks.py --release-root <directory>`. An
evolution-only release root needs `background_docs/`; Skill-only preparation
also requires `skills/` and `skill_status.tsv`.
