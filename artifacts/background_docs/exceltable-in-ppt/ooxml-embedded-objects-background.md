# General Background: Embedded Workbooks in PowerPoint

PowerPoint files are OOXML packages stored as ZIP archives. A presentation can
contain an embedded Excel workbook as a separate package part, connected through
relationships from a slide, chart, or OLE object. The displayed table or chart
may be cached separately from the workbook data, so changing one representation
does not necessarily update the other.

## Package and workbook structure

OOXML parts are connected by relationship files and declared through package
content types. Embedded workbooks retain normal spreadsheet features such as
cell values, formulas, styles, number formats, merged cells, named ranges, and
calculation settings. Formula text and cached results are distinct concepts;
some libraries preserve formulas but do not calculate new cached values.

## Safe transformation principles

A robust tool should discover the embedded part and relevant worksheet structure
from the current presentation at runtime. It should preserve unrelated package
parts, relationship targets, workbook formulas, styles, and layout unless the
instruction requires a change. Hard-coded archive paths, sheet names, cell
ranges, column meanings, or row counts are not portable.

When data is transformed, units and direction matter. Rates, percentages,
totals, and reciprocal quantities should be interpreted from their source
labels and surrounding context rather than inferred from numeric magnitude
alone. Formula dependencies may require recalculation in an engine capable of
evaluating the workbook.

## Validation

Validation should reopen both the presentation package and embedded workbook,
confirm relationship integrity, check that formulas and styles were preserved,
and compare changed cells with the requested transformation. A successful ZIP
write is not sufficient evidence that PowerPoint or Excel can consume the
result. Independent rendering or application-level reopening can reveal stale
caches and package inconsistencies.
