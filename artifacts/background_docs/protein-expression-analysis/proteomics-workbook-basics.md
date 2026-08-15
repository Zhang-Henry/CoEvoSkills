# Proteomics Workbook Basics

Quantitative proteomics tables usually require an exact two-dimensional lookup:
one key selects a protein row and another selects a sample column. Treat both as
opaque identifiers, obtain group membership from supplied metadata, and keep
missing values distinct from numeric zero.

For log-transformed measurements, follow the declared scale and comparison
direction. Compute group summaries and variability using the convention stated
by the task rather than guessing from spreadsheet defaults.

Spreadsheet libraries can write formulas without calculating their cached
values. When formulas are required, preserve them, recalculate with an available
spreadsheet engine, save, reopen in value-reading mode, and verify that the
requested cells are numeric and error-free. Discover all sheets, labels, ranges,
and output locations at runtime; this document contains none of the current
workbook's identifiers, formulas, cells, or expected values.
