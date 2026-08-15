# Demand-Side Macroeconomic Shock Analysis

This document summarizes general methods for translating an investment or
spending shock into a transparent macroeconomic scenario. It contains no
current-workbook sheet names, cell addresses, supplied observations, or
evaluator-specific values.

## Separate nominal levels, real levels, and growth rates

Nominal GDP combines real activity and the price level. A simple projection can
track real GDP and a GDP deflator separately, then obtain nominal GDP as their
product. Be explicit about whether a rate is a decimal or percentage and about
the period to which it applies. Growth rates should normally be compounded:

```text
real_gdp[t] = real_gdp[t-1] * (1 + real_growth[t])
deflator[t] = deflator[t-1] * (1 + inflation[t])
nominal_gdp[t] = real_gdp[t] * deflator[t]
```

When extending an official time series, keep supplied observations as source
values and begin projection formulas only after the final observed period.
Record the boundary between observed and projected data.

## Convert project spending into domestic demand

Imported inputs do not directly add the same amount to domestic value added.
A stylized first-round domestic impulse is:

```text
domestic_impulse = project_spending * (1 - import_content_share)
```

For a project concentrated in one industry, estimate import content from a
supply-and-use or input-output table using the commodity composition of that
industry rather than an economy-wide imports ratio. Identify rows and columns
from labels and metadata; do not assume a fixed range or column letter.

## Timing and multipliers

Allocate a multi-period project using a documented profile whose shares sum to
one. A bell-shaped profile can model ramp-up, peak construction, and ramp-down,
but its parameters must come from the scenario or an explicit modeling choice.

A multiplier represents indirect and induced activity beyond the first-round
domestic impulse. State whether it is applied contemporaneously or through a
lag distribution, and avoid double-counting project spending already embedded
in the baseline. A simple contemporaneous increment is:

```text
gdp_increment[t] = allocated_spending[t]
                   * (1 - import_content_share)
                   * multiplier[t]
```

Alternative scenarios should differ only in declared assumptions, so that the
source of each change is auditable.

## Workbook construction

Discover the supplied workbook structure at runtime:

1. inventory sheets, named ranges, tables, headers, and existing formulas;
2. locate assumption and output regions from labels rather than coordinates;
3. preserve source-table sheet names when formulas already reference them;
4. write assumptions as inputs and projected values as formulas;
5. maintain consistent units and absolute/relative references;
6. recalculate with a compatible spreadsheet engine when cached values matter;
7. reopen the result and inspect formulas, errors, and key identities.

Do not copy filenames, row counts, column letters, or exact formulas from an
unrelated example. They are properties of a particular workbook, not general
macroeconomic knowledge.

## Validation

At minimum, check:

- allocation shares sum to one;
- observed source values remain unchanged;
- projection formulas start after the last observation;
- import content lies in a meaningful range and its derivation is traceable;
- scenario deltas reconcile to their spending, import, timing, and multiplier
  assumptions;
- nominal/real unit conversions are dimensionally consistent;
- formulas contain no broken references or spreadsheet errors.

These checks support an evolved procedural Skill: the Skill must inspect a new
workbook and derive its mappings instead of carrying the current instance's
sheet names or answer values.

Public methodological background: OECD Supply and Use Tables describe supply
origins, imports, intermediate consumption, and final demand without prescribing
any benchmark workbook layout: <https://www.oecd.org/en/data/datasets/supply-and-use-tables.html>.
