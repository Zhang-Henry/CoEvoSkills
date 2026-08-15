# Pivot Tables and Demographic Data Integration in Excel

This document provides background on creating pivot tables in Excel workbooks programmatically, merging heterogeneous data sources (PDF tables and spreadsheets), computing derived columns, and the statistical concept of quartile binning. The domain context is Australian demographic data organized by Statistical Area Level 2 (SA2) regions.

## Australian Statistical Geography: SA2 Regions and States

The Australian Bureau of Statistics (ABS) organizes the country into a hierarchy of statistical areas. SA2 (Statistical Area Level 2) is the general-purpose medium-sized area classification, designed to represent communities that interact socially and economically. There are roughly 2,000 to 2,500 SA2 regions across Australia.

Each SA2 region has a stable code and a human-readable name.  ABS publications
document how codes relate to higher-level geographies.  Use the geography fields
present in the supplied sources, or a cited version of the ABS correspondence,
rather than embedding the current dataset's observed codes and state list in a
reusable procedure.

When merging datasets that each contain SA2-level records, the SA2 code serves as the natural join key. Different ABS data releases may cover slightly different sets of SA2 regions (some regions are suppressed for confidentiality or have no data), so a join between two SA2-indexed datasets will often yield fewer rows than either source has individually. The overlapping set of regions that appear in both sources is the correct basis for analysis.

## Joining Data from Multiple Sources

When two datasets share a documented stable geographic identifier, combine them
with an explicit join and audit unmatched keys on both sides.  Discover actual
column names and types from the supplied files.  Do not assume a current-file
schema from a background example.  When both sources carry a name or geography
label, compare the duplicates and preserve provenance rather than silently
choosing one.

A critical consideration is that the income data may contain suppressed or missing values. The ABS uses the marker "np" (not publishable) to indicate values that are suppressed for confidentiality, typically when the number of people in a region is too small to report without risking identification. Rows containing "np" in numeric fields cannot be used in arithmetic and must be handled appropriately -- either filtered out or treated as missing data.

## Extracting Tabular Data from PDFs

PDF is a presentation format, not a data format. Tables rendered in PDF do not carry machine-readable structure; they are laid out as positioned text and lines. Extracting tables from PDF requires heuristic detection of row and column boundaries based on the spatial positions of text characters.

Common issues when extracting PDF tables include:

- **Truncated column headers**: PDF extraction can clip or wrap long headers.
  Resolve a suspected truncation from neighboring headers, source metadata, and
  the visible page rather than using a mapping learned from the current file.
- **Multi-page tables**: A table that spans many pages will have its header row repeated on each page. When concatenating rows across pages, the repeated headers must be detected and removed so they do not appear as data rows.
- **Type casting**: All values extracted from PDF come as strings. Numeric columns (codes, populations) must be converted to appropriate numeric types before use in calculations or joins.

## Pivot Tables in Excel (openpyxl)

A pivot table is a data summarization tool that groups rows by one or more fields and applies aggregation functions to value fields. In Excel, pivot tables are backed by a **pivot cache** -- a snapshot of the source data that the pivot table reads from. The pivot cache stores field definitions (names and data types) and the actual data records.

A pivot table has three structural axes:

1. **Row fields**: The categorical field(s) placed on the row axis. Each unique value becomes a row label. For state-level demographic summaries, the row field is STATE.
2. **Column fields**: An optional categorical field placed on the column axis, creating a matrix layout. Each unique value becomes a column header. This is used when cross-tabulating two dimensions (e.g., state vs. quartile).
3. **Data fields**: The numeric field(s) being aggregated, along with their aggregation function. Common aggregation types include `sum` (add all values), `count` (count the number of records), `average`, `min`, and `max`.

The aggregation type must match what is being measured. Summing POPULATION_2023 gives total population per state. Summing EARNERS gives total earners per state. Counting rows gives the number of SA2 regions per state. These are conceptually different operations even though they all use STATE as the row field.

An important distinction: writing aggregated data directly to a worksheet as static cell values produces a **flat summary table**, not an Excel pivot table. A true pivot table is a structured object registered in the worksheet's internal pivot collection, backed by a pivot cache with field definitions. Any consumer that inspects pivot table properties -- row fields, column fields, aggregation types, cache fields -- will find nothing on a flat summary table, even if the numeric values happen to be identical to what a pivot table would produce. The output must contain actual pivot table objects, not formatted data that merely resembles a pivot.

When creating pivot tables programmatically with openpyxl, the process involves five steps. Steps 2 through 5 are all structurally required -- omitting any one of them will produce a pivot table that appears to exist but is functionally broken (empty fields, missing groupings, or no aggregation).

1. **Writing the source data** to a worksheet range, with headers in row 1 and data in subsequent rows. The range reference (e.g., "A1:I2500") will be used by the pivot cache.

2. **Creating a pivot cache** from that range. The cache has two essential parts: a source reference that locates the worksheet range and sheet name, and a **field list** that describes each column in the source data. This field list is the schema of the pivot table -- it is the name registry that all field references index into. There must be exactly **one field entry per source column**, in the same left-to-right order as the columns in the source data. Each entry stores a column name and a shared items container (which can be left empty for the engine to populate). If this field list is empty or missing, the pivot table will have no way to resolve field indices to column names, and any tool that reads the file will report an empty or broken pivot structure.

3. **Creating a pivot table definition** and configuring its **per-column pivot field entries**. The table definition carries its own list of pivot fields -- exactly one entry per source column, in the same order as the cache field list. Each pivot field entry declares the role of that source column within the pivot:
   - If the column serves as a **row grouping field**, the entry is marked with a row axis assignment.
   - If the column serves as a **column grouping field** (for matrix-style pivots), the entry is marked with a column axis assignment.
   - If the column is the **data source** being aggregated, the entry is flagged as a data field.
   - All other columns have no axis assignment and no data flag.

   This per-column role list is essential. If it is omitted or left empty, the pivot table will exist as a structural shell but have no functioning field assignments -- row fields, column fields, and data fields will all resolve as empty or missing.

4. **Populating three explicit reference lists** on the table definition:
   - **Row field references**: A list of entries indicating which source column index (or indices) appear on the row axis. For a pivot grouped by STATE, this contains one entry pointing to the positional index of STATE in the source columns.
   - **Column field references**: A list indicating which source column index appears on the column axis. For a matrix pivot cross-tabulating state and quartile, this points to the index of the quartile column. For non-matrix pivots, this list is left empty.
   - **Data field references**: A list specifying which source column is being aggregated, the aggregation function (e.g., "sum" or "count"), and a display name. The field is identified by its positional index in the source columns.

   These three reference lists work in concert with the per-column role assignments from step 3. Both must be configured consistently -- the axis markings in the pivot field entries must agree with which indices appear in the row/column/data reference lists.

5. **Attaching the cache and registering the pivot table**. The cache object must be attached to the table definition. The table definition must then be appended to the target worksheet's internal pivot collection. Each pivot table references a cache by its numeric index; when multiple pivot tables in a workbook share the same source data, they all reference cache index 0 (the first cache). The cache index on every table definition should therefore be set to 0.

## Quartile Binning Based on Value Ranges

Quartiles divide a distribution into four groups. However, there are two fundamentally different ways to define quartiles, and they produce very different results:

**Percentile-based quartiles (quantile method):** Sort all observations and divide them into four groups of approximately equal size. The 25th, 50th, and 75th percentiles of the data define the bin boundaries. Each quartile contains roughly the same number of observations. This is the standard statistical definition of quartiles.

**Range-based quartiles (equal-width binning):** Take the minimum and maximum of the data, divide that range into four equal-width intervals, and assign each observation to the interval it falls into. The bin boundaries are: min, min + range/4, min + 2*range/4, min + 3*range/4, max. The groups will generally have very unequal sizes, especially when the data is skewed.

The word "quartile" normally refers to quantile boundaries, whereas an explicit
request for four equal-width ranges describes range binning.  They are not
interchangeable.  Resolve ambiguous task wording from the full instruction and
source conventions, document the selected definition, and validate boundary
handling; a background document should not silently choose the benchmark's
current expected interpretation.

The conventional labels for quartiles are Q1 (lowest range), Q2, Q3, and Q4 (highest range). These labels must be consistent between any derived column in the source data and any column field in a pivot table that references the quartile grouping.

## Computing Derived Columns

Derived columns are new columns computed from existing data. Two common patterns appear in demographic analysis:

**Categorical binning**: Assigning each row to a category based on a continuous variable. Quartile assignment is an example: each row's MEDIAN_INCOME value is compared to the quartile boundaries and assigned a label (Q1 through Q4). The boundaries are computed once from the full dataset and then applied to every row.

**Arithmetic combination**: Computing a new numeric value from existing columns. For example, multiplying EARNERS by MEDIAN_INCOME produces a "Total" column representing an estimate of aggregate income for each region. This is a straightforward element-wise multiplication that should be performed for every row where both input values are numeric and present.

When both types of derived columns are added to a "source data" sheet, the sheet serves as an enriched version of the joined dataset that provides the raw material for pivot table analyses.

## Workbook Organization and Sheet Naming

Excel workbooks can contain multiple sheets, each serving a different purpose. A well-organized analytical workbook typically separates:

- **Source data sheets**: Contain the raw or enriched data in a flat tabular format with headers in row 1 and data in subsequent rows
- **Pivot table sheets**: Each contains a single pivot table summarizing the source data from a particular analytical angle

Sheet names must match any specification exactly, as programmatic consumers (including test suites) locate sheets by name. Case, spacing, and punctuation all matter. When an instruction specifies five sheets with particular names, the output workbook must contain exactly those sheets with exactly those names.

## Domain-Specific Nuances

- **Count and sum are distinct aggregation operations.** Counting rows gives the number of SA2 regions per state, while summing a numeric column gives the total of that column's values. The choice of aggregation function must match the analytical intent -- the two operations produce numerically plausible but semantically different results.
- **Range-based and percentile-based groups produce different assignments.**
  State the chosen definition and boundary inclusion rules, and do not infer an
  evaluator-specific choice from a worked example.
- **The ABS "np" marker indicates suppressed data.** The ABS replaces numeric values with "np" (not publishable) when cell counts are too small for confidentiality reasons. These string values cannot participate in arithmetic operations and must be filtered or treated as missing before any numeric computation is performed.
- **PDF extraction can truncate long column headers.** Confirm any correction
  against the rendered source and metadata instead of using a current-instance
  header substitution.
- **Pivot tables require two parallel field lists and three reference lists.** The cache must have a field entry for each source column (the schema), and the table definition must have a corresponding pivot field entry for each source column (the role assignments). Additionally, the table definition must populate its row field, column field, and data field reference lists. All five structures must be present and consistent. Omitting the cache field list produces a pivot with no schema; omitting the pivot field entries produces a pivot where all fields resolve as missing; omitting the reference lists produces a pivot with no grouping or aggregation. These are the most common causes of structurally broken pivot tables.
- **Geographic scope must be explicit.** Do not drop or add territories merely
  to match an expected category list.  Apply the scope declared by the task or
  cited source and report exclusions.
- **Join type affects the resulting dataset size.** If one source has regions the other lacks, an inner join will drop those rows. Understanding whether a left join, right join, or inner join is appropriate depends on what the downstream analysis requires. For pivot tables that must reference fields from both sources, only rows present in both sources can be included.
