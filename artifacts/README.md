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

`evaluations/` contains trace-free result summaries that are safe to publish.
Raw Agent conversations and Docker task sandboxes are not release artifacts.
The evidence tables collectively include at least one canonical full-score,
fresh Skill-only result for every Skill marked as validated. The historical
backfill table also records current Skill-tree and background-document hashes so
the older formal sweep remains tied to the exact released artifacts. One legacy
verifier emitted a canonical reward and per-case stdout rather than CTRF; its
row identifies that evidence format explicitly instead of implying a CTRF file.

During a run, `scripts/prepare_tasks.py` copies the selected release material
to `workspaces/<RUN_ID>/<condition>/`. Evolution may modify that workspace. A
run-specific snapshot is then stored under `outputs/<RUN_ID>/`; neither
location is a source of truth for this release bundle.

Alternative release versions can use the same layout in another directory and
be selected with `scripts/prepare_tasks.py --release-root <directory>`. An
evolution-only release root needs `background_docs/`; Skill-only preparation
also requires `skills/` and `skill_status.tsv`.
