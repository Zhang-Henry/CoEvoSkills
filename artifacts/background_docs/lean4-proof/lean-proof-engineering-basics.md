# Lean proof-engineering basics

Lean checks a proof against the declarations imported by the current source
file. Before choosing a tactic, inspect the local definitions and available
theorems in that exact environment; similar-looking declarations from another
project or library version are not interchangeable.

For recursively defined objects, induction often turns a universal statement
into a base case and a successor case. In the successor case, expose only the
definition needed for the current step, rewrite with the induction hypothesis,
and leave routine arithmetic to tactics supported by the imported libraries.
Keep side conditions such as positivity, nonzeroness, and type coercions
explicit when automation cannot infer them.

Small compile checks are more reliable than guessing tactic syntax. Preserve
the required source prefix, make the smallest proof-local edit, compile with
warnings treated as errors, and re-open the final file to confirm that no
unrelated declaration changed.
