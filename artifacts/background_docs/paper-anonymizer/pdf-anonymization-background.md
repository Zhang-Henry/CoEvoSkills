# PDF Anonymization for Blind Peer Review

This document provides background on the principles and techniques for anonymizing academic papers in PDF format to support blind (or double-blind) peer review. It covers what constitutes identity-revealing information, how PDF redaction works at the technical level, and the subtleties that distinguish a correct anonymization from a destructive or incomplete one.

## What Must Be Redacted

Blind review requires removing all information that could allow a reviewer to infer authorship. The obvious category is author names and institutional affiliations on the title page, but identity leakage extends well beyond the byline.

**Direct identifiers** include:

- **Author names** as they appear in the author block, headers, footers, and acknowledgement sections.
- **Institutional affiliations** (universities, companies, labs) listed beneath author names or in footnotes.
- **Email addresses** that contain institutional domains or personal identifiers.
- **Correspondence footnotes** such as "corresponding author" notes that name individuals.

**Indirect identifiers** are less obvious but equally deanonymizing:

- **arXiv identifiers**: Papers posted to arXiv before submission carry an arXiv ID (e.g., `arXiv:YYMM.NNNNN`). Since arXiv is publicly indexed, anyone can look up the ID and immediately find the author list. arXiv IDs may appear in headers, footers, or watermarks inserted by the arXiv compilation system.
- **DOIs and venue references**: If a paper has been previously published or accepted at a venue, its DOI or venue-specific identifiers can link directly to a public record that lists the authors. A synthetic example is `10.0000/example.paper.001`; actual identifiers must be discovered from the supplied PDFs. Venue names in a paper header can serve the same purpose.
- **Acknowledgement sections**: These commonly thank named collaborators, funding agencies with grant IDs traceable to PIs, or institutional resources. Individual names mentioned in acknowledgements who are not authors still narrow the identity pool significantly.
- **Contribution statements**: Author-linked contribution-role footnotes can reveal identity when combined with other context.

## What Must Be Preserved

Anonymization is a precision operation. The goal is to remove identity signals while keeping all scientific content intact. Over-redaction degrades the paper and can make review impossible.

**Paper body content** -- the abstract, introduction, methods, results, discussion, figures, tables, equations, and captions -- must remain fully intact. A redacted PDF should be readable as a complete scientific paper with only authorship information missing.

**Page structure** must be preserved. The output PDF should have exactly the same number of pages as the input. If redaction causes the page count to change (e.g., by deleting entire pages or collapsing whitespace), the structural integrity of the document is compromised. Similarly, the overall content length should remain substantially the same -- a redacted PDF with dramatically less text than the original suggests destructive editing rather than targeted redaction.

**Self-citations in the references section** require special treatment. In double-blind review, it is standard practice to leave the references section largely untouched. Authors cite their own prior work, and reviewers expect to see those citations. Redacting self-citations from the reference list is actually counterproductive: it creates conspicuous gaps that draw attention, and it removes citations that reviewers need to evaluate the paper's positioning in the literature. The convention is that if all direct author identifying information (names on the title page, affiliations, acknowledgements) has been removed, the mere presence of self-citations in the reference list is acceptable. The key distinction is: author names in the **byline and body** must be redacted, but author names appearing as part of **bibliographic references** should generally be left alone.

## Correct Workflow: Discover, Then Redact

Anonymization is a three-phase process: **discovery**, **redaction**, and **verification**. The most critical insight is that you must first **read and analyze the PDF content** to build an explicit list of strings to redact, then apply precise string-level redaction for each item. You do not know the author names or acknowledgement names in advance -- you must extract them from the PDF itself.

### Phase 1: Discovery -- Build the Redaction List

**Complete this entire phase before writing any redaction code.** The discovery phase is an analytical task, not a scripting task. Extract text from each PDF and read through it section by section to build a complete, explicit list of every string that must be redacted.

Some categories of identifying information (emails, arXiv IDs, DOIs) follow predictable patterns and can be found with regex. **Person names in prose — author blocks, acknowledgement sections, contribution footnotes — do not follow predictable patterns and require reading and understanding the text.** You must read the extracted text, understand its structure, and identify the specific name strings to redact. Only after the redaction list is finalized should you write the redaction script.

1. **Author block on the title page**: Extract the text from the first page. The author block typically appears between the title and the abstract. Read the names listed there -- these are the author names. Read the lines below them -- these are the affiliations. Each name and each affiliation becomes a separate entry in the redaction list.

2. **Email addresses**: Scan the extracted text (especially footnotes on the first page) for email patterns. Each email address is an entry in the redaction list.

3. **Acknowledgements section**: Locate the acknowledgements section by searching for the heading. Extract its full text. **Read every sentence carefully** to identify person names mentioned — these are proper nouns embedded in natural language sentences (e.g., after phrases like "We thank", "We are grateful to", "The authors would like to thank", "with the help of", etc.). Each person name becomes an entry in the redaction list. **This is the most commonly missed category of identity leakage.** Acknowledgement names are embedded in free-form prose and cannot be discovered by pattern matching or regex — you must read and understand the sentences to find them. Do NOT blank the entire acknowledgements section — only redact the specific identity-revealing strings within it.

4. **Contribution statements and footnotes**: Inspect the first page and footnotes for contribution-role text tied to author markers. Such text can link specific byline entries to roles and should be added to the redaction list using the exact wording discovered in the supplied PDF. Do not assume a particular stock phrase.

5. **Indirect identifiers (before References only)**: Scan pages **before the References section** for the paper's own arXiv ID (pattern: `arXiv:YYMM.NNNNN`), DOI, and venue/acceptance statements. Important: arXiv IDs and DOIs that appear **inside the References section** belong to other cited papers and must NOT be redacted -- removing them would damage the bibliography and constitute over-redaction. Only the paper's own identifiers (typically found in headers, footers, or the first page) should be removed.

6. **PDF metadata**: Read the document metadata (Author, Creator fields) to discover additional names that may appear in the text.

The output of this phase is an explicit, concrete list of strings (e.g., `["Author Name", "University Name", "arXiv:YYMM.NNNNN", ...]`). Build this list by reading the PDF content yourself, then pass the complete list to your redaction script. Every subsequent redaction must target one of these specific strings -- nothing more, nothing less.

**The redaction list must be complete and finalized before any redaction code runs.** Names discovered through reading (especially acknowledgement names) should be hardcoded into the redaction parameters — do not rely on the script to discover them at runtime. If you found a name by reading the text but your script's automated discovery would miss it, add it explicitly to the list rather than hoping the script will find it on its own.

### Phase 2: Redaction -- Precise String Matching Only

**The cardinal rule: every redaction annotation must correspond to a specific text string found via `page.search_for()`.**

For each string in the redaction list, search every page (or every page before References, depending on context) for that exact string, add a redaction annotation over the matching bounding box, and apply the redaction. This permanently removes the underlying text while preserving everything else on the page.

Libraries such as PyMuPDF (fitz) provide the two-step workflow: `page.search_for(string)` returns bounding boxes, then `page.add_redact_annot(rect)` + `page.apply_redactions()` removes the text data.

**NEVER use area-based or region-based redaction** (e.g., "redact the top 30% of page 1" or "redact from 35% height to the bottom of the acknowledgements page"). Rectangular region redaction destroys scientific content -- titles, abstracts, body text, figures, and equations that happen to fall within the rectangle are permanently lost. This is the single most common cause of over-redaction failures.

### Phase 3: Verification

After redaction, extract text from the output PDF using a text extraction tool (e.g., `pdftotext`) and confirm that:

1. **No target strings remain** -- every item from the redaction list should be absent from the extracted text.
2. **Content is preserved** -- a word-level diff between original and redacted text should show changes only at the locations of redacted strings. If more than ~50 words that are NOT on the redaction list have disappeared, the redaction was too aggressive. The goal is surgical precision, not broad coverage.

### Page-by-Page Processing

Redaction must be applied page by page. Identity-revealing information can appear anywhere in a paper, not just the first page: headers and footers may repeat author names or arXiv IDs on every page, acknowledgement sections may appear near the end, and venue identifiers may be in footnotes on any page.

## Scope of Redaction: Precision vs. Recall

A good anonymization maximizes recall (all identity-revealing strings are found and redacted) while maintaining precision (nothing else is altered). These two objectives create a natural tension.

**Under-redaction** leaves identity signals in the paper. Common causes include:

- Searching only the first page when identifiers appear throughout the document.
- Missing variant spellings or formatting of names and affiliations (e.g., the synthetic variants "Example Research University" and "Example Research Univ.").
- Overlooking indirect identifiers like arXiv IDs, DOIs, or acknowledgement names.
- Forgetting email addresses embedded in footnotes.

**Over-redaction** removes content that should remain. Common causes include:

- **Using rectangular region redaction** instead of string-level redaction. For example, blanking the top 30% of the first page to "cover the author block" will also destroy the paper title, part of the abstract, and any other content in that region. Similarly, blanking the lower half of the acknowledgements page destroys body text, figures, or equations that share that page. This is the most destructive anti-pattern and must be avoided entirely.
- Naively redacting every occurrence of an author's last name, which may also be a common English word or appear in unrelated citations. Always redact the **full name discovered in the paper** (e.g., the synthetic name "Example Researcher"), never an isolated surname token that may match unrelated occurrences.
- Redacting self-citations from the references section.
- Removing entire sections (e.g., deleting the acknowledgements section) instead of redacting only the specific person names and identifying strings within them. The surrounding text of acknowledgements ("We thank ... for their help with data collection") is not identity-revealing and should remain.
- Applying pattern-based redaction too broadly (e.g., redacting all university names rather than only the authors' affiliations).

The ideal outcome is a PDF where a word-level diff between the original and redacted text shows changes only at the locations of identity-revealing strings, with all other content preserved verbatim. A practical threshold: if more than 50 non-target words are missing from the redacted PDF compared to the original, the approach is too aggressive and needs to be rethought.

## Context-Sensitive Redaction

Not all occurrences of a given string should be treated the same way. The location within the paper matters.

**Author block (title page)**: Names and affiliations here must always be redacted. This is the primary location of authorship information.

**Headers and footers**: Some PDF templates repeat author names, paper titles, arXiv IDs, or venue names in running headers or footers. These must be checked on every page.

**Footnotes**: Contribution statements, email addresses, and funding acknowledgements often appear as footnotes on the first page or within the body.

**Acknowledgements section**: This section frequently contains names of individuals who helped with the work. These names are identity-revealing even if they are not formal authors. The correct approach is to extract the text of the acknowledgements section, identify the specific person names mentioned within it (e.g., "We thank **X** and **Y** for ..."), and add each name to the redaction list. Do not blank the entire acknowledgements section or use region-based redaction on it -- only the specific names and identifying strings should be removed.

**References section**: The entire references section should be left untouched. Author names appearing as part of bibliographic citations must be preserved. arXiv IDs and DOIs within the references belong to other cited works and must NOT be redacted -- they do not reveal the authorship of the paper being anonymized. The only identifiers that need redaction are the paper's own arXiv ID or DOI, which typically appear in headers, footers, or the first page, not in the references list.

## Technical Considerations

**True redaction removes text data from the PDF content stream, not just the visual layer.** Drawing a black rectangle over text makes it invisible to human readers but leaves the underlying text data intact in the PDF, and any text extraction tool will recover it. Proper redaction uses the annotation-then-apply workflow, which permanently removes the text operators from the content stream, ensuring the redacted content is irrecoverable.

**Redaction should modify the existing PDF in place rather than reconstructing the document from scratch.** Some approaches extract all text from the original, modify it, and generate a new PDF, but this destroys the original formatting, layout, figures, equations, and tables. The output may technically contain the right text, but it is no longer a faithful representation of the paper. In-place modification preserves the full visual and structural fidelity of the original.

**Author names in the body and byline are distinct from author names in bibliographic references.** Applying a blanket search-and-replace for author last names across the entire document will redact those names from the references section, damaging citation integrity. Conversely, excluding the references section from all redaction may leave non-citation identifiers (like arXiv IDs embedded in reference entries) exposed. The standard approach distinguishes between these two contexts.

**Pattern matching must account for PDF text representation variability.** A discovered name may not be found if the PDF stores it with ligatures, unusual Unicode characters, or hyphenation across a line break. Affiliations may appear in both full and abbreviated forms (for example, the synthetic pair "Example Institute of Technology" and "Example Tech"), and both variants need to be targeted. Testing redaction with text extraction is essential to catch cases where the search pattern did not match the PDF's internal text representation.

**The output document must be structurally identical to the input except for the specific redacted strings.** Deleting pages, collapsing sections, blanking rectangular regions, or stripping all metadata can change the page count and content length of the document. A reviewer receiving a significantly shorter or restructured paper will immediately notice the discrepancy, and critical content may be lost in the process. The only acceptable modification is the removal of specific identity-revealing text strings via the search-and-redact-annotation workflow.
