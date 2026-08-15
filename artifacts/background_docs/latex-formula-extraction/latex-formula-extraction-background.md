# Extracting Display-Mode LaTeX Formulas from PDF Documents

This document provides background on how LaTeX formulas are represented in PDF files, the challenges of faithfully recovering their source markup, and the conventions for cleaning and correcting extracted formulas.

## Display-Mode vs. Inline Formulas

LaTeX distinguishes two presentation modes for mathematics:

- **Inline mode** places a formula within the flow of text, delimited by single dollar signs (`$...$`) or `\(...\)`. The formula shares the baseline and vertical space with the surrounding paragraph.
- **Display mode** places a formula on its own line, centered and visually separated from surrounding text. It is delimited by double dollar signs (`$$...$$`), `\[...\]`, or environments such as `equation`, `align`, and `gather`.

When a task asks for "formulas in their own line," it refers exclusively to display-mode formulas. Inline expressions embedded within sentences should not be extracted. The visual cue is clear: a display-mode formula occupies its own horizontal space on the page, often with vertical whitespace above and below, and may carry an equation number in the right margin.

A single PDF page may contain zero, one, or several display-mode formulas. Not every page in a research paper contains them; introductory, concluding, and reference sections typically have none, while methodology and derivation sections may have several.

## PDF-to-LaTeX Recovery: Why It Is Lossy

PDF is a presentation format, not a source format. When a LaTeX document is compiled to PDF, the mathematical typesetting engine (typically TeX's math layout algorithms) converts symbolic source code into positioned glyphs, rules, and spacing instructions. The original LaTeX source string is not preserved in the PDF.

Recovering LaTeX from a PDF therefore requires **reverse engineering** the visual layout back into plausible source code. Specialized tools use OCR, layout analysis, and heuristic or learned models to produce candidate LaTeX strings. Several properties of this conversion are important to understand:

1. **Multiple valid representations.** The same visual rendering can be produced by many different LaTeX source strings. For example, `\frac{a}{b}` and `\dfrac{a}{b}` render identically in display mode. Similarly, `\left( ... \right)` and `\bigl( ... \bigr)` may produce the same glyph sizes. Any of these are acceptable as long as they render to the same visual output.

2. **OCR artifacts.** Extraction tools may introduce spurious characters, misread symbols (confusing `\zeta` with `\xi`, or `\ell` with `l`), or fail to recognize command boundaries. These errors are typically visible when the extracted formula is rendered -- the output will differ from the PDF.

3. **Structural ambiguity.** Subscripts, superscripts, and nested groupings must be inferred from spatial relationships. A subscript that appears close to a base character could be attached to the wrong symbol if the spatial analysis is off by even a few points.

4. **Tag and numbering noise.** Many papers use numbered equations. The equation number (e.g., "(1)", "(2)") is not part of the formula itself but appears on the same line. Extraction tools often pick up these numbers as part of the formula content. The `\tag{...}` command or appended digits like `\quad (1)` are common artifacts that must be stripped.

## Cleaning Extracted Formulas

Raw extraction output almost always requires post-processing before it matches the visual content of the PDF. The standard cleaning steps are:

**Remove equation numbering artifacts.** Tags such as `\tag{1}`, `\tag{2.3}`, or inline numbering like `\quad (4)` or `\qquad(3)` should be removed entirely. These are not part of the mathematical content; they are formatting artifacts from the document's equation numbering system.

**Strip trailing punctuation.** In running text, a displayed formula is often followed by a comma or period that belongs to the sentence, not to the mathematics. For example, a paper might write:

For example, a paper might introduce an unrelated synthetic expression with the display-mode formula `$$F(x)=\int_0^x h(t)\,dt,$$` and then continue the sentence on the next line.

The trailing comma after the displayed expression is grammatical punctuation and should be removed from the extracted formula. The same applies to trailing periods. This example illustrates cleanup mechanics only and is not drawn from the document to be processed.

**Normalize whitespace.** Multiple spaces, tabs, or newlines within a formula should be collapsed to single spaces. LaTeX ignores extra whitespace in math mode, so this does not change the rendered output, but it ensures consistent formatting in the output file.

**Preserve mathematical content exactly.** Cleaning must not alter the mathematical meaning. Renaming variables, reordering terms, simplifying expressions, or "improving" notation are all out of scope. The goal is faithful reproduction of what appears in the PDF, not mathematical optimization.

## Identifying and Correcting Typographical Errors in Formulas

Research papers occasionally contain typographical errors in their formulas. A formula extraction task may require identifying these errors and providing corrected versions. It is critical to understand what constitutes a correctable error versus what should be left alone.

**Correctable errors (syntax/typographical):**

- **Mismatched brackets.** LaTeX requires that every opening delimiter has a corresponding closing delimiter of the same type. A formula containing `\left\{...\right]` has mismatched brackets -- the opening brace does not pair with the closing square bracket. There is no universal rule that says which side should be changed. Infer the intended pair from repeated notation elsewhere in the document, the mathematical role of the group, and the visible glyphs in the PDF. Round parentheses `()`, square brackets `[]`, curly braces `\{\}`, angle brackets, and norm or absolute-value bars each have their own conventional uses.
- **Misspelled LaTeX commands.** An unrecognized command such as `\alhpa` where the visible symbol and surrounding notation clearly support `\alpha`, or `\sinn` where the typeset operator is plainly `\sin`, is a typographical error. Confirm against the rendered page rather than correcting every unfamiliar macro, since papers can define legitimate custom commands.
- **Missing or extra grouping braces.** If a subscript or superscript is missing its braces (e.g., `x_ij` where `x_{ij}` was intended), this is a syntax error that changes the rendering.

**Non-correctable issues (leave as-is):**

- **Wrong physics or mathematics.** If a formula uses a plus sign where a minus sign is physically correct, that is a scientific error, not a typographical one. Do not "fix" the physics.
- **Stylistic choices.** Using `\cdot` vs. `\times`, or `\hbar` vs. `h`, or choosing a particular variable name -- these are authorial decisions, not errors.
- **Display preferences.** Switching between `\frac` and `\dfrac`, or adding `\displaystyle`, or changing delimiter sizes for aesthetic reasons, falls outside the scope of error correction.

The key principle is: **only correct errors that would cause the formula to render differently from what the author clearly intended**, as evidenced by the surrounding context. A bracket mismatch is unambiguously wrong because it produces a visually broken formula. A sign error might be physically wrong but visually intentional.

## Output Format and Deduplication

When writing extracted formulas to a file, each formula occupies exactly one line, wrapped in `$$` delimiters:

Each formula occupies exactly one line, wrapped in double-dollar delimiters -- for example, `$$formula_1$$` on the first line, `$$formula_2$$` on the second line, and so on. There is one formula per line with no blank lines between them.

The file should contain **no duplicate lines**. If the same formula appears on multiple pages of the PDF (e.g., restated in different sections), it should appear only once in the output. Deduplication should be based on the actual content between the `$$` delimiters.

When corrected versions of formulas are included, they are appended after all the original formulas. The original (uncorrected) version is kept in the file as well; the corrected version is an additional entry. This means a formula with a typographical error will have two representations in the output: the original extraction and the fixed version.

**Worked example.** Suppose a PDF contains three display-mode formulas. The second formula has a visibly mismatched delimiter such as `\left\{u>0\right]`, and the third contains a clearly misspelled command such as `\alhpa`. If the page and surrounding notation establish the intended brace and symbol, the output retains all three original extractions and then appends the two corrected versions. The extraction pipeline must **never silently replace** an erroneous formula with its corrected form.

## Rendering Equivalence as the Ground Truth

Two LaTeX strings are considered equivalent if they produce **identical visual output** when rendered by a standard math typesetting engine. This is a stronger criterion than string equality and a weaker criterion than semantic equality:

- `\frac{a}{b}` and `\dfrac{a}{b}` are rendering-equivalent in display mode (same visual output).
- `a + b` and `b + a` are **not** rendering-equivalent (different visual output), even though they are mathematically equal.
- `\sum_{i=1}^{N}` and `\sum_{i=1}^N` are rendering-equivalent (braces around a single token are optional).

This means there is flexibility in how extracted formulas are written, as long as the rendered output matches the PDF. An agent does not need to recover the exact original LaTeX source; it needs to produce LaTeX that renders identically to what appears in the paper.

Tools like MathJax can be used to render LaTeX to SVG or bitmap images, enabling pixel-level comparison of two candidate formula strings. This is often more reliable than string comparison, since many surface-level differences in LaTeX source produce identical rendered output.

## Technical Considerations

**Display-mode vs. inline distinction.** The most fundamental distinction in formula extraction is between display-mode formulas (occupying their own line, centered, visually separated from text) and inline formulas (embedded within running text, sharing the baseline with prose). Only display-mode formulas are the target of extraction. The visual layout of the PDF page is the definitive guide: if a formula shares its line with prose text, it is inline.

**Equation numbering artifacts.** Tags like `\tag{1}` or trailing sequences such as `\quad (3)` are numbering artifacts from the document's equation system, not mathematical content. Standard cleaning removes these entirely, as they do not contribute to the formula's mathematical meaning.

**Bracket matching in LaTeX.** LaTeX's delimiter pairing system requires that every opening delimiter has a corresponding closing delimiter of the same type. A formula with mismatched delimiters such as `\left[...\right)` is syntactically broken and produces a visually incorrect rendering. The appropriate correction matches both delimiters to the same type, determined by the surrounding mathematical context. The full set of delimiters that can appear with `\left`/`\right` includes: parentheses `()`, square brackets `[]`, curly braces `\{\}`, **angle brackets `\langle` and `\rangle`** (common in physics for inner products, expectation values, and Dirac notation), vertical bars `|` (absolute value), double vertical bars `\|` (norms), and the invisible delimiter `.` (used for one-sided matching). A bracket-validation implementation must cover **all** of these types — omitting angle brackets is a particularly common bug since `\langle`/`\rangle` are multi-character commands rather than single characters, making them easy to miss in regex patterns. When fixing mismatches by replacing delimiters, processing replacements in **reverse position order** (from the end of the string backward) avoids corrupting earlier string indices. After extraction, a systematic bracket-validation pass should check every `\left`/`\right` pair and flag mismatches for correction.

**Scope of error correction.** The distinction between typographical errors and mathematical content is fundamental. Correctable errors are those that affect the rendering in ways the author clearly did not intend (mismatched brackets, misspelled commands, missing grouping braces). Changes to mathematical content (signs, variable names, term ordering) or stylistic preferences (delimiter sizing, display commands) are outside the scope of correction, even if they might be scientifically wrong.

**Multi-column PDF layouts.** Research papers frequently use two-column formatting. PDF extraction tools may have difficulty with column boundaries, potentially missing formulas in the second column or merging content across columns. Each column is an independent layout region and should be processed separately. Correct column detection requires analyzing the horizontal distribution of text bounding boxes across the page: a two-column layout exhibits a clear gap (gutter) near the horizontal center where no text appears. Formulas in the second column may have different centering properties than those in the first column, so centering-based detection heuristics must be applied relative to the column boundaries, not to the full page width.

**Robust display-mode detection.** Centering alone is not sufficient to identify display-mode formulas. Some display-mode formulas may be left-aligned within their column (common in certain journal styles), and some centered text may not be a formula. The most reliable detection combines multiple signals: vertical whitespace above and below the candidate line, absence of prose words on the same line, presence of mathematical symbols or operators, and optionally an equation number on the right margin. Review ambiguous candidates against the rendered page: both omissions and extra non-formula lines make the extraction unfaithful.

**Deduplication of repeated formulas.** A formula that appears on multiple pages of the PDF (e.g., restated in different sections) should appear only once in the output file. Distinct formulas that happen to look similar (e.g., the same structure with different variables) are separate entries and should each be included.

**Organization of original and corrected formulas.** The output file has two logical sections: all original formulas first, followed by corrected versions. A corrected formula is an additional line appended after the originals, not a replacement. Both the original and corrected versions are present when a correction is warranted.
