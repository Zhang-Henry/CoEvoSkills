# General Principles for GDP-Weighted Trade Analysis

This document summarizes public, reusable concepts for spreadsheet-based trade
analysis. It does not provide workbook-specific row mappings, cell values,
country or series identifiers, formulas copied from a target workbook, or an
expected result.

## Net exports as a share of GDP

Under the expenditure approach to national accounts, net exports are exports
minus imports. A normalized trade measure divides net exports by nominal GDP:

`net exports share = (exports - imports) / GDP`

Multiply a ratio by 100 when the requested presentation unit is percentage
points. Keep the unit convention consistent through descriptive statistics and
weighted aggregation, and do not mix source series expressed in different
scales without converting them first.

## Two-key spreadsheet lookup

Many economic workbooks store observations in a matrix: a series identifier
selects a row and a period selects a column. A reliable lookup therefore uses
both keys instead of assuming that source and destination rows have the same
order. Spreadsheet functions such as `INDEX` with two `MATCH` operations,
`XLOOKUP` combined with a header lookup, or equivalent formulas can implement
this pattern.

Before filling a range, inspect the workbook at runtime and verify:

- which cells contain the destination series identifiers and periods;
- which source row and header ranges contain the corresponding keys;
- whether year headers are stored as numbers, dates, or text;
- whether source values and missing-value markers are numeric;
- whether every requested key resolves exactly once.

Use absolute or mixed references deliberately so a formula copied across rows
and columns continues to point to the correct key and source ranges. Treat a
missing or duplicate match as a validation failure rather than silently using a
nearby row.

## Descriptive statistics

Minimum, maximum, median, arithmetic mean, and percentiles summarize the
cross-sectional distribution for a period. Spreadsheet percentile functions
have inclusive and exclusive variants with different interpolation rules, so
use the variant requested by the workbook or instruction. Keep the observation
set identical across related statistics unless missing-data handling is
explicitly declared.

## Weighted means

For observations `x_i` with non-negative weights `w_i`, the weighted mean is:

`sum(x_i * w_i) / sum(w_i)`

GDP weighting uses GDP values from the same entity and period as each trade
share. Align the value and weight arrays by stable entity keys, not by an
assumed row order. Check that the arrays have equal length, that the weight sum
is positive, and that missing values are handled consistently. In a
spreadsheet, `SUMPRODUCT` is a common implementation, but the formula ranges
must cover matching entities in matching order.

## Formula and workbook integrity

When the task requests formulas, preserve formulas rather than replacing them
with unexplained literals. Formula-writing libraries generally do not calculate
workbooks themselves; cached values can therefore be stale until a spreadsheet
engine recalculates the file. Validation should distinguish formula structure
from calculated values and, when possible, recalculate a copy in a compatible
engine before reopening it to check for formula errors.

Preserve the existing workbook structure and presentation unless changes are
requested. Do not add sheets, macros, or unrelated formatting. After writing,
reopen the saved workbook and verify that formulas occupy the intended blank
regions, source sheets remain unchanged, styles are preserved, and all
downstream formulas reference the intended periods and entities.

## End-to-end validation

A reusable workflow should derive workbook coordinates and keys from the
runtime file, write formulas according to the declared task, and then perform
independent checks such as:

1. every requested row/period key has a unique source match;
2. copied formulas use the correct relative and absolute references;
3. net-export shares have plausible units and no divide-by-zero errors;
4. summary ranges cover the intended observations;
5. weighted values and weights remain aligned by entity and period;
6. the saved workbook reopens cleanly with its original layout intact.

These checks describe general spreadsheet engineering practice. The actual
workbook remains the only source for its identifiers, coordinates, inputs, and
computed outputs.
