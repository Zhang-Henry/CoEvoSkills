# SEC Form 13F Filings and Institutional Holdings Analysis

This document provides background on SEC Form 13F filings, the EDGAR bulk data format for institutional holdings, and the analytical techniques needed to extract fund-level and security-level insights from these filings.

## What Is Form 13F?

Form 13F is a quarterly report mandated by the Securities and Exchange Commission (SEC) under Section 13(f) of the Securities Exchange Act of 1934. Every institutional investment manager exercising investment discretion over at least $100 million in qualifying securities must file Form 13F within 45 days of the end of each calendar quarter. The filing discloses the manager's equity holdings in SEC-designated "Section 13(f) securities," which include exchange-traded stocks, certain convertible debt, and listed options.

Form 13F is the primary public window into the portfolios of hedge funds, mutual funds, pension funds, banks, and insurance companies. Because filings are public and machine-readable, they are widely used for competitive intelligence, factor construction, and regulatory analysis.

### What 13F Does and Does Not Reveal

Form 13F discloses long positions in qualifying equity securities. It does **not** disclose:

- Short positions
- Fixed-income holdings (bonds, treasuries) unless they are convertible
- Foreign-only-listed securities
- Derivatives positions beyond listed options (e.g., swaps, forwards)
- Cash or cash equivalents
- Private investments

Therefore, the total "Assets Under Management" (AUM) derived from a 13F filing represents only the long equity book reported to the SEC, not the fund's true total AUM. This distinction matters when interpreting aggregate VALUE figures.

## EDGAR Bulk Data Format

The SEC distributes 13F data in quarterly bulk downloads as a set of tab-separated value (TSV) files. Each quarterly archive contains several interrelated tables joined by a common key: `ACCESSION_NUMBER`.

### Core Tables and Their Relationships

**COVERPAGE.tsv** serves as the filing-level index. Each row represents one 13F filing and contains the filing manager's name (`FILINGMANAGER_NAME`), address, report type, and the accession number that uniquely identifies the filing. This is the table to query when looking up which manager filed and obtaining the accession number needed to retrieve that manager's holdings.

**INFOTABLE.tsv** contains the individual security holdings. Each row represents one line item in a manager's 13F schedule: the security name (`NAMEOFISSUER`), its class description (`TITLEOFCLASS`), its CUSIP identifier, the market value (`VALUE`), the number of shares or principal amount (`SSHPRNAMT`), and voting authority details. A single filing (one accession number) will have many rows in INFOTABLE -- one per security position. This is the largest file by far, often containing millions of rows across all filers.

**SUBMISSION.tsv** provides metadata about when each filing was submitted, the CIK (Central Index Key) of the filer, and the reporting period.

**SUMMARYPAGE.tsv** provides the filer's own summary: total number of table entries and total portfolio value. This can serve as a cross-check against computed aggregates.

**OTHERMANAGER.tsv and OTHERMANAGER2.tsv** identify co-managers who share discretion over reported positions.

**SIGNATURE.tsv** captures signatory information.

### The Accession Number as Join Key

The `ACCESSION_NUMBER` is the universal foreign key across all tables. A typical analytical workflow is:

1. Search COVERPAGE to identify a manager and obtain their accession number for the quarter of interest.
2. Filter INFOTABLE by that accession number to retrieve all holdings for that manager.
3. Optionally join with SUMMARYPAGE or SUBMISSION for additional context.

Accession numbers change every quarter. A given fund will have a different accession number for Q2 than for Q3. When comparing across quarters, you must independently look up the accession number in each quarter's COVERPAGE data.

## Finding a Fund Manager: Name Matching

The `FILINGMANAGER_NAME` field in COVERPAGE contains the legal name as reported by the filer. Names are not standardized -- the same entity may appear with variations across quarters or may have a formal legal name that differs from its commonly known name. Examples of variation include:

- Abbreviation differences: "LLC" vs. "L.L.C.", "Inc" vs. "Inc."
- Capitalization differences: "Renaissance Technologies LLC" vs. "RENAISSANCE TECHNOLOGIES LLC"
- Subsidiary distinctions: a well-known parent name might not match the exact filing entity

When searching for a specific manager, exact string matching often fails. Fuzzy matching (e.g., using token-based similarity or edit-distance algorithms) against the `FILINGMANAGER_NAME` column is the standard approach. The general strategy is to normalize case (lowercase both the query and the candidate names), then rank candidates by similarity score, and select the best match above a reasonable threshold.

After identifying the correct `FILINGMANAGER_NAME`, extract its `ACCESSION_NUMBER` to proceed with holdings analysis.

## Understanding Holdings in INFOTABLE

### The VALUE Column

The `VALUE` column in INFOTABLE represents the market value of each position. Since January 3, 2023, this value is reported **rounded to the nearest dollar**. Prior to that date, values were reported in thousands of dollars. For data from 2023 onward, no multiplication is needed -- the VALUE column is already in dollars.

To compute a manager's total AUM from their 13F filing, sum the VALUE column across all rows matching their accession number. This gives the aggregate market value of all reported long equity positions.

### The TITLEOFCLASS Column and Identifying Stocks

Each holding has a `TITLEOFCLASS` that describes the type of security. The 13F covers many types of securities, and not all of them are common stocks. The TITLEOFCLASS field is filer-reported and uses informal, inconsistent abbreviations.

"Stocks held" is not a uniquely defined SEC field. Before counting, derive the intended security universe from the task instruction or declare a defensible analytical policy. Inspect the distinct `TITLEOFCLASS` labels in the relevant filing instead of importing a fixed whitelist from an unrelated benchmark. Use `PUTCALL`, `SSHPRNAMTTYPE`, issuer descriptions, and SEC documentation as supporting evidence because a filer-provided label can be ambiguous.

Also state the counting unit. A row count, a count of unique CUSIPs, and a count of issuer-level positions can differ when a filing contains multiple lots or share classes. This background intentionally supplies neither a task-specific label whitelist nor a hidden choice among those counting rules.

### CUSIP: The Security Identifier

CUSIP (Committee on Uniform Securities Identification Procedures) is a 9-character alphanumeric code that uniquely identifies a security. The first 6 characters identify the issuer, the 7th and 8th identify the specific issue, and the 9th is a check digit.

CUSIPs are essential for:

- **Cross-quarter comparison**: Since issuer names and title descriptions may vary between filings, CUSIP provides a stable identifier to match the same security across Q2 and Q3.
- **Cross-fund comparison**: To find all funds holding a specific security, filter INFOTABLE by that security's CUSIP.
- **Aggregation**: When a fund holds multiple lots or classes of the same underlying security, grouping by CUSIP and summing VALUE yields the total position size.

### Shares, Principal Amount, and Options

The `SSHPRNAMTTYPE` column distinguishes between share-based positions ("SH") and principal-amount-based positions ("PRN"). The `PUTCALL` column, when populated, indicates whether a position is a put option, call option, or blank (equity). Options positions have a TITLEOFCLASS that might say "CALL" or "PUT", and the PUTCALL column confirms this. When analyzing pure equity holdings, you typically exclude rows where PUTCALL is populated or where SSHPRNAMTTYPE is "PRN".

## Comparing Holdings Across Quarters

A key analytical task is measuring how a fund's portfolio changed between two quarters. The procedure is:

1. **Obtain accession numbers independently for each quarter.** Look up the fund in each quarter's COVERPAGE separately, since accession numbers are quarter-specific.
2. **Load holdings for each quarter** by filtering INFOTABLE by the respective accession number.
3. **Filter to comparable security types.** Restrict both quarters to the same set of security classes (e.g., only equity/stock types) so the comparison is apples-to-apples.
4. **Aggregate by CUSIP.** A fund may have multiple INFOTABLE rows for the same CUSIP (e.g., different voting authority buckets or lots). Group by CUSIP and sum VALUE to get the total dollar position per security per quarter.
5. **Perform an outer merge on CUSIP.** An outer join ensures you capture securities that were held in only one quarter (new buys or complete sells). Fill missing values with zero for the absent quarter.
6. **Compute changes.** The dollar change for each security is VALUE_Q3 - VALUE_Q2. Positive values indicate increased investment; negative values indicate reduced positions. Rank by absolute dollar change to identify the largest moves.

### Handling New and Exited Positions

When a security appears only in Q3 (not in Q2), its Q2 value should default to zero, making the change equal to the full Q3 value -- representing a new position. Conversely, a security only in Q2 represents a complete exit, with a negative change equal to its Q2 value. An outer merge naturally captures both cases, but you must explicitly handle missing values (fill with zero) before computing differences.

## Searching for Securities Across All Filers

To find which funds hold a particular security, you need the security's CUSIP. If you only know the company name (e.g., "Palantir"), you can search the INFOTABLE's NAMEOFISSUER column. However, issuer names vary across filers, so CUSIP-based filtering is more reliable once you have identified the correct CUSIP.

After filtering INFOTABLE by CUSIP, group by `ACCESSION_NUMBER` and sum `VALUE` to get each filer's total position in that security. Then join back to COVERPAGE on `ACCESSION_NUMBER` to retrieve the `FILINGMANAGER_NAME` for each filer. Sorting by VALUE descending identifies the largest holders.

When multiple rows exist per accession number for the same CUSIP (due to shared/sole voting authority splits or multiple lots), aggregation by accession number is essential to avoid double-counting or undercounting a fund's total exposure.

## Amendments and Duplicate Filings

The COVERPAGE contains an `ISAMENDMENT` column ("Y" or "N") and related fields for amendment type. A fund may file an original report and then file one or more amendments that restate or add to the original. When multiple filings exist for the same manager in the same quarter, you must decide which to use:

- If only interested in the most recent picture, take the latest filing (often the amendment).
- If the amendment type is "RESTATEMENT," the amendment fully replaces the original.
- If the amendment type adds new holdings, both filings may be needed.

For most analytical purposes, taking the first (or only) non-amendment filing per manager per quarter is the simplest approach, but be aware that some managers may have multiple accession numbers in the same quarterly dataset.

## Practical Considerations

**VALUE column units by era.** Before 2023, 13F values were reported in thousands of dollars, and many historical references and tutorials reflect this convention. For filings from 2023 onward, VALUE is reported in whole dollars. The correct interpretation depends on the filing date, and applying the wrong unit assumption produces results off by three orders of magnitude.

**Case normalization in name matching.** Filing manager names are not case-normalized in the raw EDGAR data. Standard practice is to normalize both the search query and the candidate names to the same case (typically lowercase) before comparison, ensuring that legitimate matches are not missed due to capitalization differences.

**TITLEOFCLASS classification requires an explicit policy.** The field is free-form text with inconsistent abbreviations. Normalize case and whitespace, inspect the labels present in the selected filing, and cross-check other structured fields. Avoid an undocumented universal whitelist: whether depositary receipts, funds, units, options, or multiple share classes belong in a reported count depends on the requested definition.

**CUSIP-level aggregation before cross-quarter comparison.** A fund may report the same security across multiple INFOTABLE rows within a single filing (e.g., shares with sole voting authority in one row and shared voting authority in another). Standard methodology aggregates by CUSIP and sums VALUE before performing any cross-quarter comparison, ensuring accurate position sizes and meaningful quarter-over-quarter changes.

**Quarter-specific accession number lookup.** Accession numbers are unique to each quarterly filing. Each quarter requires an independent lookup in that quarter's COVERPAGE data, as reusing an accession number from one quarter to query another quarter's data will return no results.

**Outer join for complete position change analysis.** An inner join between Q2 and Q3 holdings drops securities that were newly purchased in Q3 or completely sold from Q2. Since new large positions often represent the biggest dollar increases, an outer join with zero-fill for missing values captures both new entries and complete exits, providing accurate change ranking across the full portfolio.
