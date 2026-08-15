# GitHub Repository Activity Analytics

This document summarizes public GitHub data semantics and reproducible counting
methods.  It contains no precomputed values for a repository or month and does
not redefine the task's time-window language to match an evaluator shortcut.

## Define the cohort and event window separately

First select the cohort requested by the instruction, such as pull requests or
issues created within a half-open UTC interval `[start, end)`.  Then calculate
each requested outcome from the appropriate event field:

- creation uses `createdAt`;
- merge timing and merge duration use `mergedAt`;
- closure during a period uses `closedAt`;
- current open/closed status uses `state`.

These are different questions.  A record created in one month and closed in a
later month belongs to the creation cohort but not to the earlier month's
closure-event count.  Follow the instruction's wording rather than silently
substituting current state for an event-date condition.

## Pull request states and durations

GitHub exposes merged pull requests distinctly from unmerged closed pull
requests.  Count the fields or states defined by the task and document whether
"closed" includes merged items; do not assume the convention when the contract
defines separate merged and closed fields.

For a merged pull request, time to merge is `mergedAt - createdAt`.  Compute in
UTC, retain full precision for every duration, average over records with a valid
merge timestamp, and round only the final aggregate.

When finding a top contributor, group by a stable author login and handle null
authors from deleted accounts.  Choose and document a deterministic tie rule if
the instruction does not supply one.

## Issue labels

Labels are objects with names.  For substring-based classification, normalize
the label name and search token consistently, then mark an issue once even if
several labels match.  Keep the label rule independent from the issue's closure
event rule.

## Retrieval completeness

CLI and API list operations are paginated and may default to open records only.
Request all relevant states, follow pagination until no next page remains, and
deduplicate by node ID or repository-local number.  Check boundary timestamps
explicitly so records at midnight are counted once.

Before writing output, retain an internal audit table with record ID, creation,
merge, closure, state, author, and labels.  Reconcile aggregate counts against
that table, validate JSON types and required keys, and write to the path stated
in the instruction.

Public references:

- GitHub GraphQL `PullRequest` object:
  <https://docs.github.com/en/graphql/reference/objects#pullrequest>
- GitHub GraphQL `Issue` object:
  <https://docs.github.com/en/graphql/reference/objects#issue>
- GitHub pagination guidance:
  <https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api>
