# PDF Table Extraction and Tabular Data Differencing

This document provides background on extracting structured tabular data from PDF documents, loading Excel workbooks, and performing accurate row-level differencing between two versions of the same dataset.

## How Tables Are Stored in PDF

PDF is a page-description format, not a data format. A PDF file encodes glyphs at precise (x, y) coordinates on a page. There is no native "table" object in the PDF specification; what a human sees as a table is merely a collection of text fragments and optional ruling lines arranged in a grid-like pattern. This has several consequences for extraction:

1. **No column metadata.** Unlike a spreadsheet, a PDF does not store column names, data types, or cell boundaries as first-class objects. The extraction tool must infer column boundaries from the spatial positions of text and lines.

2. **Text ordering is not guaranteed.** PDF rendering engines may emit text fragments in any order. A naive "read all text" approach often interleaves characters from different columns or rows. Table-aware parsers reconstruct row/column structure by clustering text based on vertical and horizontal alignment.

3. **Multi-page tables.** When a table spans multiple pages, headers may or may not be repeated. The extraction logic must detect page breaks and stitch rows from successive pages into a single coherent table, while avoiding double-counting repeated headers.

4. **Numeric values are text.** Every value in a PDF -- whether it represents a salary, a year count, or a department name -- is stored as a text string. After extraction, numeric fields must be explicitly cast to the appropriate type (integer or float) before any comparison can be meaningful.

## PDF Table Extraction Approaches

Several Python libraries exist for pulling tables out of PDFs, and they use fundamentally different strategies:

**Stream-based (pdfplumber).** Analyzes the positions of characters and, optionally, ruling lines to identify cell boundaries. Works well for tables with clear columnar alignment. The library returns each page's tables as lists of lists of strings. Key considerations include setting the correct page range and choosing between lattice mode (uses lines) and stream mode (uses whitespace gaps).

**Java-bridge (tabula-py).** A Python wrapper around the Tabula Java library. Like pdfplumber, it supports both lattice and stream detection modes. It requires a JRE to be installed. Tabula returns DataFrames directly, which can simplify downstream processing but may introduce unexpected type coercions.

**OCR-based (pytesseract + pdf2image).** Rasterizes each PDF page to an image and runs optical character recognition. This is necessary only when the PDF contains scanned images rather than embedded text. OCR introduces character recognition errors (e.g., "0" vs "O", "1" vs "l") and is far slower. It should be a last resort.

Regardless of the library, the extracted output is raw text. Post-processing is always required to clean headers, strip whitespace, normalize column names, and convert numeric strings to actual numbers.

## Reading Excel Files

Excel workbooks (.xlsx) use the Office Open XML format, which stores data in typed cells. Unlike PDF, Excel preserves data types: a cell marked as numeric will be read as an integer or float, a date cell as a datetime object, and a text cell as a string.

The two primary Python libraries are:

- **openpyxl** reads and writes .xlsx files natively. It returns cell values with their stored types.
- **pandas** (via its Excel reader backed by openpyxl) loads a sheet into a DataFrame with type inference.

Key considerations when reading Excel data:

- **Header row identification.** By default, pandas treats the first row as column headers. If the sheet has title rows or blank rows before the actual header, the header parameter or row-skipping configuration must be set correctly.
- **Numeric precision.** Excel internally stores all numbers as IEEE 754 double-precision floats. An unrelated synthetic integer like 54321 might be read as 54321.0. Before comparison, ensure consistent typing (e.g., cast to int if the source data is known to be integral).
- **Trailing whitespace.** Text cells may contain leading or trailing spaces that are invisible in the Excel UI. Stripping whitespace from string columns prevents false mismatches.

## Set-Based Row Differencing

Given two versions of a dataset -- an "old" version and a "new" version -- differencing means identifying three categories of change:

1. **Deleted rows.** Rows present in the old dataset whose primary key does not appear in the new dataset.
2. **Added rows.** Rows present in the new dataset whose primary key does not appear in the old dataset.
3. **Modified rows.** Rows whose primary key appears in both datasets but where one or more field values differ.

The standard algorithm works as follows. First, collect the set of primary keys from each dataset. Compute three subsets: **deleted keys** are those present in the old dataset but absent from the new dataset (old keys minus new keys). **Added keys** are those present in the new dataset but absent from the old dataset (new keys minus old keys). **Common keys** are those present in both datasets (the intersection of old and new keys). Then, for each key in the common set, iterate over every field and compare the old value to the new value. If they differ, record a modification entry noting the key, the field name, the old value, and the new value.

This approach requires a reliable primary key. In employee datasets, this is typically an employee ID field. The ID must be normalized (e.g., consistent zero-padding, consistent string format) across both sources before set operations.

## Type-Aware Value Comparison

The most error-prone step in cross-format differencing is comparing values that originated from different storage formats. A synthetic numeric field with value 54321 might appear as:

- The string `"54321"` from PDF extraction
- The string `"54,321"` from PDF extraction (with thousands separator)
- The integer `54321` from Excel
- The float `54321.0` from Excel/pandas

Robust comparison requires:

1. **Stripping formatting characters.** Remove commas, currency symbols, and percent signs from PDF-extracted strings before conversion.
2. **Casting to a common type.** For fields known to be numeric (salary, years of experience, scores), convert both values to int or float before comparison. For text fields (names, departments), compare as stripped strings.
3. **Avoiding floating-point traps.** When comparing numeric values, either cast both to integers (if the domain is integral) or use a tolerance justified by the source precision. Direct equality comparison on floats can produce false mismatches due to representation differences.
4. **Consistent string normalization.** When comparing text fields, apply the same normalization to both sides: strip whitespace, consider case sensitivity (decide whether an unrelated label such as "Logistics" and "logistics" should be treated as the same), and handle encoding differences (e.g., en-dash vs hyphen).

## Handling Large Multi-Page PDF Tables

When a PDF table contains hundreds or thousands of rows, it will span many pages. Extraction must account for:

- **Repeated headers.** Many PDF-generating tools repeat column headers on every page. If not filtered, these header rows will appear as data rows in the extracted table. A common approach is to extract each page's table independently, then drop rows whose values match the expected column headers.
- **Row fragmentation.** If a row's content wraps to a new line within the PDF, the extraction tool may split it into two rows. Post-processing must detect and merge such fragments, typically by checking for rows with mostly empty cells followed by continuation text.
- **Page boundary artifacts.** Some PDF tools insert page numbers, footers, or other non-table content between table segments. These must be filtered out before concatenation.
- **Concatenation order.** Pages must be processed in order. If the tool returns pages out of order or if multi-threaded extraction is used, the resulting table will have shuffled rows. Always sort or process pages sequentially.

After extraction and concatenation, validate the result by checking that the number of columns is consistent across all rows and that the primary key column contains no duplicates (unless the source data genuinely has duplicates).

## Output Formatting and JSON Serialization

When writing comparison results to JSON:

- **Numeric fields must be numbers, not strings.** JSON distinguishes between `54321` (number) and `"54321"` (string). If the task specifies numeric output for salary or year fields, ensure the values are serialized as JSON numbers. This means the value in the data structure must be an integer or float, not a string.
- **Text fields must be strings.** Department names, employee names, and similar fields should remain as JSON strings.
- **Sorting for determinism.** When the output specifies a sort order (e.g., by employee ID), sort the lists before serialization. JSON serialization preserves list order, so sorting must happen at the data structure level, not at the serialization level.
- **Employee ID format preservation.** IDs like "EMP00002" are strings with zero-padded numeric suffixes. They must be output as strings, not as integers. Stripping the prefix or removing leading zeros will produce incorrect IDs.

## Important Technical Details

**PDF extraction requires validation before downstream use.** PDF extraction is inherently noisy. Validation steps -- checking column count, verifying header names, inspecting a sample of rows -- are a standard part of any PDF table extraction pipeline, because skipping them often leads to silently misaligned data where values from one column are attributed to another.

**Cross-format value comparison requires type normalization.** The single most common source of false positives (reporting a change that does not exist) and false negatives (missing a real change) in cross-format differencing is comparing a string from PDF extraction against a typed value from Excel without first converting both to the same type. For example, the synthetic string "54321" and the integer 54321 are semantically identical but are not equal under direct comparison in most programming languages.

**Multi-page PDF extraction must cover all pages.** When a table spans multiple pages, the extraction code must process every page of the table. Processing only the first page, or failing to filter out repeated headers (which would be counted as data), results in an incorrect dataset that causes real rows to appear as deleted or modifications to go undetected.

**The direction of the diff determines the semantics of old and new values.** In a two-version comparison, "old_value" and "new_value" are relative to which file is treated as the baseline. If the PDF is the old backup and the Excel is the current version, then "old_value" comes from the PDF and "new_value" comes from the Excel. Reversing this assignment produces reports where every modification has its old and new values swapped, which is semantically incorrect even though the set of modified IDs is correct.

**Employee IDs with leading zeros must be treated as strings throughout.** Employee IDs such as "EMP00002" contain leading zeros that are significant. If the numeric portion is ever parsed as an integer (yielding 2 instead of "00002"), the ID will not match across datasets, causing the employee to appear as both deleted from the old set and added in the new set -- a phantom deletion and addition pair.

**Repeated header rows in multi-page PDFs must be deduplicated.** When a PDF table spans multiple pages and headers are repeated on each page, these repeated header rows must be removed during extraction. If left in place, they produce phantom data entries where the column header values appear as data values, corrupting both the deletion and modification analysis.
