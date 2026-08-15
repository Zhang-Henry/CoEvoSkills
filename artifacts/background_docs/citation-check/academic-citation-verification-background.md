# Verifying Academic Citations: Detecting Fake and Hallucinated References

This document provides background on how academic citations work, how fake or hallucinated references are constructed, and the practical techniques for distinguishing genuine citations from fabricated ones.

## The Anatomy of a BibTeX Citation

A BibTeX entry encodes structured metadata about a published work. Each entry type (`@article`, `@inproceedings`, `@book`, etc.) has expected fields, and the combination of these fields provides multiple independent verification signals.

Key metadata fields and what they encode:

| Field | Purpose | Verification Value |
|---|---|---|
| `doi` | Digital Object Identifier — persistent link to the published work | High: DOIs are registered with specific registrants and resolve to publisher pages |
| `author` | List of authors | Medium: real authors have publication histories in databases |
| `title` | Title of the work | High: exact titles can be searched in academic databases |
| `journal` / `booktitle` | Publication venue | High: real venues are indexed and have ISSN/ISBN records |
| `year`, `volume`, `number`, `pages` | Publication coordinates | Medium: must be consistent with the venue's actual publication history |
| `url` | Link to the work | Medium: can be checked for liveness, but URLs can rot |
| `isbn` / `issn` | Identifier for the publication series | Medium: can be validated against registries |
| `biburl` / `bibsource` | Provenance of the BibTeX entry itself | Low-medium: entries from DBLP or other indexers suggest genuine records |

A well-formed citation is not necessarily a real one. Fake citations can have syntactically correct BibTeX with plausible-looking metadata across all fields. Verification requires checking whether the metadata corresponds to an actual published work.

## The DOI System and How It Exposes Fakes

The Digital Object Identifier (DOI) system is the single most reliable signal for citation verification. Understanding its structure is essential.

### DOI Structure

A DOI has the form `10.XXXX/suffix`, where:

- `10.` is a mandatory prefix identifying it as a DOI
- `XXXX` is the **registrant code** — a number assigned to a specific organization (publisher, institution, or service) by the DOI Foundation through a registration agency
- The `/suffix` is assigned by the registrant and can have any format

### Registrant Codes Are Assigned, Not Arbitrary

Every legitimate DOI begins with a registrant code that was officially assigned to a real organization. Major academic publishers have well-known registrant codes:

| Registrant Code | Organization |
|---|---|
| `10.1038` | Nature Publishing Group (Springer Nature) |
| `10.1126` | AAAS (Science) |
| `10.1109` | IEEE |
| `10.18653` | Association for Computational Linguistics (ACL Anthology) |
| `10.1145` | ACM |
| `10.1007` | Springer |
| `10.1016` | Elsevier |
| `10.1371` | PLOS |
| `10.1073` | PNAS |
| `10.1162` | MIT Press |

Registrant codes are **not sequential numbers** and **not freely chosen**. A DOI starting with a registrant code that does not correspond to any registered organization is a strong indicator of fabrication. Visual appearance alone is not proof: every unfamiliar prefix should be checked against the DOI registrant directory and the full DOI should be resolved. Synthetic placeholders such as `10.<unverified-registrant>/example` must never be treated as evidence about entries in the supplied bibliography.

### DOI Resolution

A legitimate DOI resolves to a publisher landing page when accessed via `https://doi.org/<doi>`. The resolution can be verified programmatically:

- **HTTP resolution**: A GET request to `https://doi.org/10.1038/s41586-021-03819-2` should redirect (HTTP 302/303) to the publisher page. A 404 or failure to resolve indicates the DOI does not exist.
- **CrossRef API**: The CrossRef works endpoint returns metadata for registered DOIs. A 404 response means the DOI is not in the CrossRef registry. CrossRef is the primary DOI registration agency for academic content.
- **DataCite API**: Some DOIs (especially for datasets) are registered through DataCite rather than CrossRef. If CrossRef returns nothing, checking DataCite may be appropriate, though for journal articles and conference papers CrossRef is the standard.

### What DOI Verification Reveals

When a DOI resolves successfully, the returned metadata can be cross-checked against the BibTeX entry:

- Do the authors match?
- Does the title match?
- Does the journal/venue match?
- Do the year, volume, and pages match?

Discrepancies between the DOI metadata and the BibTeX fields suggest either a transcription error or a fabrication where a fake DOI was attached to plausible-looking metadata.

## Academic Database Verification Beyond DOIs

Not all citations have DOIs. Books, older papers, and some conference proceedings may lack them. In these cases, other databases serve as verification sources.

### Semantic Scholar

Semantic Scholar indexes over 200 million papers and provides a free API. Searches can be performed by title, author, or paper ID. A paper that cannot be found in Semantic Scholar is not necessarily fake (coverage gaps exist), but combined with other suspicious signals, absence from Semantic Scholar is informative.

### Google Scholar

Google Scholar has the broadest coverage of any academic search engine, indexing papers from publishers, preprint servers, institutional repositories, and personal websites. However, it has no public API, making automated verification more difficult. Manual or scraping-based approaches are possible but rate-limited.

### DBLP

DBLP is the authoritative index for computer science publications. BibTeX entries that include `biburl` and `bibsource` fields pointing to DBLP were likely exported from DBLP itself, which is a strong provenance signal — DBLP entries correspond to real, indexed publications. Entries lacking DBLP provenance in a CS-focused bibliography warrant closer scrutiny through other means.

### Publisher Databases

Individual publisher databases (IEEE Xplore, ACM Digital Library, SpringerLink, ACL Anthology, etc.) are authoritative for their own publications. A paper claiming to be published in an IEEE journal can be verified directly against IEEE Xplore.

## Signals That a Citation May Be Fabricated

Fake citations are typically generated by language models or manually constructed to fill bibliography gaps. They tend to exhibit characteristic patterns:

### Structural Red Flags

- **Unresolvable DOI**: The DOI does not resolve via doi.org or return metadata from CrossRef. This is the strongest single signal.
- **Suspicious registrant code**: The DOI prefix does not correspond to a known publisher or registration agency.
- **No DOI at all**: While some real citations lack DOIs (especially books and older papers), a modern journal article or conference paper without a DOI is unusual.
- **Missing provenance fields**: Real BibTeX entries exported from DBLP, Google Scholar, or publisher sites often carry metadata like `biburl`, `bibsource`, or `timestamp`. Manually constructed fake entries typically lack these.

### Content Red Flags

- **Vague or overly generic titles**: Titles like "A Comprehensive Review of [Broad Topic]" or "Advances in [Field] for [Application]" that could describe thousands of different papers. Real papers tend to have more specific, distinctive titles.
- **Generic author names**: Common Western names without distinctive middle initials, uncommon name combinations, or names that do not appear in any author index. Real authors in a given subfield can usually be found via Semantic Scholar or DBLP.
- **Non-existent venues**: Journal names or conference proceedings that sound plausible but do not correspond to any indexed venue. The journal name should be searchable and have an ISSN.
- **Inconsistent metadata**: Page numbers, volumes, or years that do not match the actual publication history of the claimed venue. For example, claiming a volume number that the journal had not reached by the claimed year.

### Contextual Red Flags

- **Mismatch between entry type and venue**: Using `@article` for what should be a conference paper, or `@inproceedings` for a journal article.
- **Suspiciously round or sequential page numbers**: Real page numbers reflect the actual layout of a publication and are rarely round numbers.
- **No web presence**: A thorough search across Google Scholar, Semantic Scholar, DBLP, and the claimed publisher yields no trace of the paper, its authors (in combination), or its venue.

## Verification Strategy: A Practical Approach

Effective citation verification combines multiple signals rather than relying on any single check. A systematic approach works through signals from strongest to weakest:

1. **DOI-first triage**: For entries with DOIs, attempt resolution and CrossRef lookup. Entries with valid, resolving DOIs that return matching metadata are almost certainly genuine. Entries with DOIs that fail to resolve or return mismatched metadata are highly suspect.

2. **DOI registrant analysis**: For DOIs that fail resolution, examine the registrant code. An unrecognized registrant code is a fabrication indicator independent of resolution failure.

3. **Database cross-referencing**: For entries without DOIs (or with failed DOIs), search by title in Semantic Scholar, DBLP, and Google Scholar. A paper that appears in none of these databases — especially a recent one — warrants skepticism.

4. **Author verification**: Check whether the claimed authors have other indexed publications, particularly in the same field. Author names that appear nowhere in academic indexes are suspicious.

5. **Venue verification**: Confirm the journal or conference exists and is indexed. Check whether the volume/year combination is plausible.

6. **Provenance signals**: Entries with DBLP `biburl`/`bibsource` fields, ACL Anthology URLs, or other indexer provenance are likely genuine exports from those databases.

## Key Distinctions in Practice

- **A syntactically correct DOI is not necessarily a registered DOI.** A DOI that follows the 10.XXXX/suffix format is not necessarily registered with any agency. The registrant code must correspond to a real organization, and the full DOI must resolve to a publisher page to confirm its validity.

- **Minor formatting differences between BibTeX entries and database records are normal.** BibTeX entries may have slight title variations (capitalization, special characters, subtitle formatting) compared to the canonical database entry. Normalization of titles and author names is necessary before declaring a mismatch.

- **No single database has complete coverage of all academic publications.** A paper missing from Semantic Scholar might still be indexed by DBLP or Google Scholar. Multiple negative results across several databases are needed to build confidence that a citation is fabricated, as individual databases have known coverage gaps.

- **The distinction between "cannot verify" and "confirmed fake" is meaningful.** Some real papers -- especially very recent ones, those from smaller venues, or those in non-English languages -- may have limited database presence. Inability to find a paper is weaker evidence than finding a non-resolving DOI with an unregistered prefix.

- **Metadata verification through DOIs and databases is more reliable than subjective title assessment.** Human judgment about whether a title "sounds real" is unreliable. Many genuine papers have generic-sounding titles, and sophisticated fabrications can produce highly specific ones. Structured metadata checks provide far stronger evidence.

- **BibTeX titles often contain LaTeX formatting that must be cleaned before searching.** Titles frequently include LaTeX commands, curly braces for capitalization preservation, and escape sequences for special characters. These formatting artifacts must be stripped before using the title as a search query in any database.
