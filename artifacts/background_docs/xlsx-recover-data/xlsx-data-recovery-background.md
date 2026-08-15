# General Recovery of Missing Spreadsheet Values

Missing spreadsheet values can sometimes be reconstructed from formulas, labels, repeated facts, and mathematical constraints elsewhere in a workbook. This document gives general spreadsheet-recovery knowledge only. It does not describe the current workbook's sheets, cell addresses, year range, missing values, precision policy, or solution order.

## Discover the workbook before assuming a layout

An `.xlsx` file is an OOXML package containing workbook metadata, worksheet XML, styles, shared strings, relationships, and sometimes formula definitions or cached results. Libraries such as `openpyxl` can expose these structures without launching a desktop spreadsheet application.

Start by inspecting, rather than assuming:

- sheet names and dimensions;
- merged cells, hidden rows or columns, and formulas;
- row and column labels;
- cell values, data types, number formats, and styles; and
- repeated entities or measures across sheets.

Labels are safer anchors than hard-coded row or column numbers. Different sheets can place equivalent facts at different coordinates.

## Common algebraic relationships

The following public formulas are often useful, but they apply only when labels or existing formulas show that the workbook uses them.

### Totals

If a total equals the sum of components, one unknown component can be recovered as

\[
x = total-\sum known\ components.
\]

### Relative change

For a previous value \(p\) and current value \(c\), relative percentage change is commonly

\[
g=100\frac{c-p}{p}.
\]

When \(p\neq0\), the relationship can be inverted: \(c=p(1+g/100)\).

### Proportions

If a component \(x\) is represented as a percentage \(s\) of total \(T\), then

\[
s=100\frac{x}{T},\qquad x=T\frac{s}{100}.
\]

### Compound growth

For start value \(a\), end value \(b\), and \(n\) equal-length intervals,

\[
CAGR=100\left[\left(\frac{b}{a}\right)^{1/n}-1\right].
\]

The interval count must be inferred from the labeled observations, not from an assumed calendar window.

### Means and differences

An arithmetic mean is the sum divided by the number of included observations, while a simple difference is one value minus another. Which observations belong to a summary must be established from labels or formulas in the workbook.

## Build a dependency model

Treat each unknown cell as a variable and each evidenced relationship as a constraint. A useful procedure is:

1. Inventory unknown or invalid cells without changing the original workbook.
2. Identify formulas, labels, repeated values, and cross-sheet relationships that constrain each unknown.
3. Solve variables whose dependencies are already known.
4. Add the recovered value to the working model and repeat until no further variable is unlocked.
5. For simultaneous constraints, solve the small algebraic system rather than guessing an order.

Cross-sheet dependencies are not necessarily circular. One sheet may independently determine a value needed by another, even if a different relationship points in the reverse direction.

## Precision and ambiguity

Displayed percentages and totals may be rounded while underlying values are not. Infer precision from cell number formats, neighboring values, existing formulas, and consistency checks. Keep full precision during intermediate calculations and round only when writing a value under an evidenced convention.

An inverse calculation based on a rounded percentage can admit several candidate source values. Use independent workbook constraints to disambiguate them. If evidence is insufficient for a unique value, do not invent one.

Distinguish blank cells, formula errors, strings, and numeric values. A textual placeholder is not numeric and should never silently participate in arithmetic.

## Preserve workbook integrity

When editing programmatically:

- change only the cells that must be recovered;
- preserve sheet names, formulas, styles, merged ranges, and unrelated metadata;
- write numeric results as numeric cell values rather than text; and
- save to the exact output path requested by the task.

Be aware that some libraries preserve formulas but do not calculate them. Cached values may therefore remain stale until recalculated by a compatible spreadsheet engine.

## Verification

After recovery, reload the saved workbook and confirm that:

- no targeted placeholder remains;
- every inserted value satisfies all applicable independent constraints;
- totals, ratios, changes, and repeated cross-sheet facts agree within evidenced precision;
- cell types and formats remain appropriate; and
- no unrelated cell or workbook structure changed.

The current workbook's schema and answers must come entirely from runtime inspection and derivation.
