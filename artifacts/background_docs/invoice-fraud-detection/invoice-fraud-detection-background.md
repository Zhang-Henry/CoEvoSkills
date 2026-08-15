# Invoice Fraud Detection in Accounts Payable

This document provides background on the principles of invoice fraud detection within an accounts payable workflow, covering how invoices are validated against master data sources and the types of discrepancies that indicate fraudulent or erroneous submissions.

## The Three-Way Match: Invoices, Vendors, and Purchase Orders

The foundation of accounts payable fraud detection is the **three-way match** -- the practice of cross-referencing an incoming invoice against two authoritative data sources before approving payment:

1. **Vendor Master File**: A registry of all approved vendors, containing each vendor's official name, unique identifier (Vendor ID), and authorized banking details (such as an IBAN). This is the single source of truth for who the organization does business with and where payments should be directed.

2. **Purchase Order (PO) Register**: A log of all authorized purchases. Each PO record ties a specific PO number to a vendor (via Vendor ID) and an approved monetary amount. The PO represents a pre-authorized commitment to spend.

3. **The Invoice Itself**: A payment request submitted by a vendor, typically containing the vendor's name, the amount due, the vendor's bank account identifier (IBAN), and a reference to the purchase order that authorized the work or goods.

The validation process compares each field on the invoice against the corresponding authoritative record. A legitimate invoice will match on every dimension: the vendor is known, the IBAN is on file for that vendor, the PO number exists, the amount aligns with the PO, and the PO belongs to the vendor named on the invoice. A discrepancy on any of these dimensions is a red flag.

## Fraud Categories and Their Detection Logic

Invoice fraud manifests through several distinct patterns. Each targets a different link in the three-way match chain. In practice, a single invoice may exhibit multiple anomalies simultaneously, so detection systems must apply checks in a defined priority order and report the most significant (typically the first applicable) finding.

### Unknown Vendor

An invoice lists a vendor name that does not appear in the vendor master file. This is the most fundamental check -- if the organization has no record of the vendor, the invoice is immediately suspect regardless of what other fields say. The vendor may be entirely fictitious, or it may be a real entity that has not been onboarded through proper procurement channels.

**Why this is checked first**: If the vendor is unknown, all downstream checks (IBAN, PO, amount) become meaningless because there is no authoritative record to compare against. An unknown vendor short-circuits the entire validation pipeline.

### IBAN Mismatch

The vendor name matches an entry in the vendor master file (the vendor is known), but the bank account identifier on the invoice differs from the IBAN on file for that vendor. This is a hallmark of payment redirection fraud -- an attacker impersonates a legitimate vendor but substitutes their own bank account to intercept the payment. Even a single-character difference in an IBAN is significant; IBAN validation is an exact-match operation, not a fuzzy one.

**Why this comes before PO checks**: Banking details are a vendor-level attribute. If the IBAN is wrong, it does not matter whether the PO is valid -- the payment would go to the wrong account. IBAN verification sits at the vendor identity layer, above the transaction layer.

### Invalid Purchase Order

The invoice references a PO number that does not exist in the purchase order register. This means the expenditure was never authorized. The invoice may be an attempt to charge for goods or services that were never ordered, or it may reference a fabricated PO number. When a PO number is completely absent from the invoice (no PO referenced at all), this also falls into the invalid PO category since there is no authorization record to validate against.

### Amount Mismatch

The PO exists and is linked to the correct vendor, but the monetary amount on the invoice does not match the amount recorded on the PO. This can indicate overbilling, where the vendor charges more than what was agreed upon. In accounts payable, small rounding differences are tolerated (typically less than one cent), but any discrepancy beyond the tolerance threshold is flagged. The comparison is between the invoice total and the PO-authorized amount, using absolute difference.

### Vendor-PO Mismatch

The PO number is valid and the amount matches, but the PO is assigned to a different vendor than the one on the invoice. This suggests that one vendor is attempting to claim payment for another vendor's purchase order -- a form of PO hijacking. This check requires resolving the vendor name on the invoice to a Vendor ID (via the vendor master file) and comparing it against the Vendor ID recorded on the PO.

## Vendor Name Resolution and Fuzzy Matching

A critical challenge in invoice processing is that vendor names on invoices rarely match the vendor master file exactly. Variations arise from abbreviations ("Ltd" vs. "Limited", "Inc." vs. "Incorporated"), minor typos, extra whitespace, and differences in punctuation or capitalization. A naive exact-string comparison would flag many legitimate invoices as having unknown vendors.

**Fuzzy string matching** addresses this by computing a similarity score between the invoice vendor name and each name in the vendor master file. Common algorithms include:

- **Levenshtein distance / edit distance**: Counts the minimum number of single-character edits (insertions, deletions, substitutions) needed to transform one string into the other.
- **Token-based similarity (e.g., token sort ratio)**: Splits names into tokens, sorts them, and compares. This handles reordering ("Acme Corp International" vs. "International Acme Corp").
- **Ratio-based scoring**: Produces a 0--100 score where 100 is an exact match. Libraries like rapidfuzz or fuzzywuzzy implement these efficiently.

The matching process works as follows: for each invoice vendor name, compute the similarity score against every vendor in the master file and take the highest-scoring match. If the best score exceeds a confidence threshold, treat it as a match and proceed with that vendor's records for subsequent checks. If no vendor scores above the threshold, classify the invoice vendor as unknown.

Choosing the right threshold is a balancing act. Too high and legitimate variations are missed (false positives for "Unknown Vendor"). Too low and genuinely different entities are incorrectly matched (false negatives -- a fraudulent vendor slipping through). There is no universal score cutoff: tokenization, scorer choice, name population, and language all change the score distribution. Calibrate a decision rule from labeled examples when available; otherwise inspect the best and runner-up matches, require corroborating identifiers, and leave ambiguous cases unresolved rather than importing a fixed threshold from an unrelated dataset.

RapidFuzz's public API documentation defines scorer outputs and an optional caller-selected `score_cutoff`; it does not prescribe a domain-wide business-name cutoff: <https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html>.

## Extracting Structured Data from PDF Invoices

Invoices are often received as PDF documents, with one invoice per page in a multi-page file. Before any validation logic can run, the raw PDF content must be parsed into structured fields. This extraction step is a prerequisite and a common source of errors.

### Text-Based PDFs vs. Scanned Images

- **Text-based PDFs** contain embedded text layers that can be extracted directly using PDF parsing libraries. Each page's text can be retrieved and parsed with string operations or regular expressions.
- **Scanned/image PDFs** contain only raster images and require Optical Character Recognition (OCR) to convert pages to images and then extract text. OCR introduces additional error modes (misread characters, merged fields).

### Field Extraction Strategy

Each invoice page typically contains a small set of key-value pairs: vendor name, total amount, IBAN, and PO number. Extraction approaches include:

- **Line-by-line parsing**: Read all text on a page, split by lines, and match known field prefixes (e.g., "From:", "Total", "Payment IBAN:", "PO Number:").
- **Regular expressions**: Define patterns for each field type. Amounts often follow currency symbols or specific prefixes. IBANs follow a known alphanumeric pattern. PO numbers follow a prefix convention.
- **Table extraction**: If the invoice uses a tabular layout, PDF libraries with table extraction capabilities can extract structured table data directly.

Regardless of approach, handle the full document page-by-page and make the
internal versus human-facing page-index convention explicit. Distinguish a
truly absent field, a malformed identifier, and a literal sentinel or
placeholder. Preserve the raw source value for audit, and emit null only when
the task contract or a documented schema says that the observed representation
means “missing”; there is no universal rule that every invalid identifier is
null.

## Priority-Ordered Evaluation

When an invoice exhibits multiple fraud indicators simultaneously, the detection system must report only the single most significant reason. This requires applying checks in a fixed priority order and stopping at the first match.

The rationale for priority ordering is rooted in the dependency chain of the three-way match:

1. **Vendor identity** must be established first. If the vendor is unknown, no other checks are meaningful.
2. **Banking details** are checked next because even a valid vendor with the wrong bank account represents an immediate payment risk.
3. **PO validity** comes third -- the authorization must exist before its details can be compared.
4. **Amount correctness** is checked against the PO, so the PO must be valid first.
5. **Vendor-PO linkage** is the most specific check, requiring all prior conditions (known vendor, correct IBAN, valid PO, correct amount) to have passed.

This ordering ensures that the reported reason reflects the root cause rather than a downstream symptom. For example, an invoice from an unknown vendor might also reference a non-existent PO, but the fundamental issue is that the vendor itself is not recognized.

## Structuring the Fraud Report

The output of a fraud detection system is typically a structured report listing only the flagged invoices. Clean invoices that pass all checks are excluded from the report. Each entry in the report should contain:

- **Page reference**: Which invoice (by page number) was flagged, enabling traceability back to the source document.
- **Extracted fields**: The vendor name, amount, IBAN, and PO number as read from the invoice, preserving exactly what was on the document.
- **Fraud reason**: The single applicable reason from the priority-ordered evaluation.

For invoices where a field is missing or inapplicable (e.g., no PO number on an invoice flagged as "Invalid PO"), that field should be represented as null rather than omitted or fabricated.

## Practical Considerations

Several important details affect invoice fraud detection accuracy:

- **Case sensitivity and whitespace in exact-match fields**: IBANs and PO numbers are compared using strict exact matching after normalizing whitespace and case. This normalization prevents false mismatches from formatting differences, while the underlying comparison remains strict -- unlike vendor names, IBANs and PO numbers are not subject to fuzzy matching.

- **Tolerance-based monetary comparison**: Monetary values extracted from PDFs (often as strings) must be parsed to numeric types. Direct equality comparison of floating-point numbers is unreliable due to representation limitations. Standard practice is to use a tolerance-based comparison (absolute difference less than a small epsilon value) rather than strict equality.

- **Absent PO references and invalid PO references are both forms of "Invalid PO"**: An invoice that contains no PO reference at all and an invoice that references a PO number not found in the register both indicate the same fundamental issue -- no valid authorization exists. The detection logic handles both cases under the same category.

- **Vendor name resolution uses the name field, not identifiers**: Fuzzy matching compares the invoice vendor name against the vendor **name** column in the master file, not against Vendor IDs or other identifiers. After resolving the name to a vendor record, the Vendor ID from that record is used for subsequent PO cross-referencing.

- **Single-reason reporting per invoice**: When multiple fraud indicators apply to a single invoice, the highest-priority reason is the one reported. The priority-ordered evaluation described above ensures that the most fundamental issue is captured. Reporting a single reason per invoice is the standard convention in accounts payable fraud detection.

- **Page indexing conventions in PDF processing**: PDF libraries typically use 0-based page indexing internally, while invoice reports conventionally use 1-based indexing. The standard approach adjusts for this offset so that page references in the report match the human-readable page numbering of the source document.

- **Exhaustive page processing**: Multi-page PDFs must be processed in their entirety. Every page in the document represents a distinct invoice and must be evaluated independently, including pages that may be difficult to parse.

- **Null representation for missing fields**: If a field cannot be extracted from the invoice, it is represented as null in the output. Placeholder values (such as "N/A" or "UNKNOWN") are not used, as they introduce false data that can cause incorrect matches or misclassifications in downstream processing.
