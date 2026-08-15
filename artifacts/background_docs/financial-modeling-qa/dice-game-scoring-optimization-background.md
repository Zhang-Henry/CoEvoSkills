# General Background: Rule-Grounded Spreadsheet Analysis

This note covers transferable methods for answering a question from a large
spreadsheet plus a supplied rule document. It does not describe the current
workbook's sheets, offsets, rows, game outcomes, missing records, tie cases, or
final answer.

## Treat supplied rules as authoritative

When a task provides a PDF or other rule document, extract and cite the rules
from that artifact at runtime. Do not substitute a remembered variant of a game
or assume that familiar category names have standard definitions. Translate
each rule into a small, independently testable scoring function before applying
it to the workbook.

If a score depends on assigning limited categories or resources across several
observations, independent greedy choices can be suboptimal. Model the joint
assignment explicitly. For small groups, enumerate valid assignments; for
larger groups, use dynamic programming, matching, or an integer program. Test
the optimizer on unrelated synthetic examples whose optimum can be checked by
hand.

## Discover spreadsheet structure

Spreadsheet formatting is not a reliable schema. A robust reader should:

1. inspect workbook and worksheet metadata without assuming a sheet name;
2. locate candidate headers by normalized text and expected data types;
3. map semantic fields to discovered columns rather than fixed letters;
4. preserve explicit record and group identifiers;
5. distinguish formulas, cached values, blank cells, merged cells, and labels;
6. reconcile row counts and group cardinalities before aggregation.

Do not regroup later records by position merely because one observation appears
to be missing. First determine whether parsing, coercion, hidden rows, formulas,
or merged cells caused the omission. If the supplied artifacts do not determine
a required value, do not invent it.

## Validate the computation

Keep a transparent intermediate table containing the source identifier, parsed
inputs, rule-derived component scores, selected assignment, and aggregate for
each group. Useful checks include:

- every accepted numeric cell lies in the domain declared by the supplied rules;
- every source identifier appears in exactly the expected groups;
- limited categories or resources are not reused illegally;
- an exhaustive and an optimized implementation agree on small synthetic cases;
- recomputing aggregates from the intermediate table reproduces the final scalar.

Pairing, tie handling, incomplete-group policy, and the sign of a reported
difference must come from the task instruction or supplied rule document. They
must not be inferred from a previous workbook, hidden test, or remembered
answer. Write only the output format requested by the instruction.
