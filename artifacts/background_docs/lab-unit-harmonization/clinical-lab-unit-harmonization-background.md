# Clinical Laboratory Unit Harmonization

This document gives general background for harmonizing clinical measurements
reported in different unit systems. It deliberately does not contain a table of
current-dataset labels, evaluator ranges, or row-by-row expected conversions.

## Unit identity comes before numeric conversion

The same analyte may be reported in conventional mass concentration units or
SI molar units. A safe harmonizer represents a measurement as at least:

- analyte identity, including specimen and subtype;
- numeric value and reported unit;
- source laboratory or source system when available;
- target unit and conversion provenance.

Names that share a word are not necessarily interchangeable. Total and ionized
calcium, total and direct bilirubin, free and total thyroid hormones, and serum
and urine measurements are distinct analytes. Resolve identity before applying
a factor.

## Dimensional derivation

For mass-to-molar conversions, derive the factor from the analyte's molecular
weight and the volume prefixes. For pure scale changes such as g/dL to g/L or
ng/mL to ng/L, derive the factor from SI prefixes. Pressure conversions use a
physical unit constant. Record the source and direction of every factor.

A useful implementation pattern is a registry whose entries contain:

```text
canonical analyte name
accepted aliases
source unit
target unit
forward conversion function
inverse conversion function
provenance
```

Prefer a unit library or a reviewed registry over scattered numeric literals.
Validate each entry with a synthetic round trip: converting a value forward and
then backward should recover the original within stated numeric tolerance.

Some quantities are numerically unchanged between commonly used systems. These
may include dimensionless ratios, percentages, enzyme activities reported in
the same unit, and monovalent-ion values where mEq/L is numerically equal to
mmol/L. Verify analyte valence and unit semantics rather than generalizing this
rule to every electrolyte.

## Detecting mixed units without an answer table

When a source unit column is reliable, use it. If unit metadata is missing, a
numeric value alone may be insufficient to identify the unit. Use converging
evidence:

1. source-level patterns across many records;
2. the distribution and scale of the analyte;
3. companion measurements from the same record;
4. physiologic plausibility ranges from cited clinical references;
5. whether a candidate conversion produces a coherent source distribution.

Do not hard-code a benchmark-wide Min/Max table. Reference intervals vary with
assay, specimen, population, age, sex, and clinical setting; diseased
populations can legitimately exceed healthy intervals. If a project needs
plausibility bounds, load them from a versioned, cited configuration and keep
them separate from the conversion registry. Ambiguous records should be flagged
for review rather than forced through whichever factor happens to land inside a
range.

Treat unit inference as constrained model selection, not unrestricted curve
fitting. Generate candidates only from an analyte-specific registry. In
log-space, a pure scale conversion appears as a cluster separation close to the
log of that analyte's admissible factor; source-system grouping or reported-unit
metadata should corroborate the same split. Compare the identity model with the
admissible conversion models, penalize unnecessary conversions, and retain an
ambiguity state when competing models have similar support. A smoother pooled
distribution is not evidence that a conversion is semantically valid.

The reusable procedure should therefore separate three operations:

1. resolve a column to an analyte and specimen using names and descriptions;
2. retrieve only public source/target unit pairs valid for that analyte;
3. decide among identity, conversion, or unresolved using several independent
   signals, then validate dimensional and inverse-conversion invariants.

This procedure may discover current column names and source clusters at runtime,
but a background document or reusable registry should not contain the current
dataset's thresholds, row assignments, converted values, or expected output.

## Parsing and data quality

Normalize representation before conversion:

- preserve missingness rather than treating it as zero;
- handle decimal comma only when source locale supports that interpretation;
- accept scientific notation with a strict numeric parser;
- retain the original value and unit for traceability;
- reject non-finite values unless the task contract says otherwise;
- convert at full precision and round only the final reported value.

Dropping every row with any missing field is not a universal rule. Apply the
task's missing-data policy and keep unrelated analytes when appropriate.

## Validation strategy

A reusable harmonizer should be tested with synthetic, non-benchmark examples:

- forward and inverse round trips for every registry entry;
- identity conversions;
- alias and specimen disambiguation;
- values on both sides of a unit-scale boundary;
- ambiguous values that must remain unresolved;
- locale and scientific-notation parsing;
- proof that the input artifact is not modified in place unless requested.

After processing real data, compare source and target distributions, count
conversions by analyte and source, and inspect outliers. These checks reveal
direction errors, double conversion, and accidental application of one
analyte's factor to another without supplying the current instance's answers.

## Public references

- NIST Guide to the SI, amount of substance, molar mass, and concentration:
  <https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-8>
- Unified Code for Units of Measure (UCUM), including units used in clinical
  medicine: <https://unitsofmeasure.org/ucum>
