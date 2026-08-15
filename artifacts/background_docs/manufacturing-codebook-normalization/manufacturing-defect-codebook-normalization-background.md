# Manufacturing Defect Codebook Normalization

This document describes general methods for mapping noisy manufacturing defect
text to a controlled codebook. It contains no record IDs, component names,
signal names, product-specific codes, current log fragments, score cutoffs, or
expected output distributions.

## Treat normalization as constrained entity linking

Free-text defect notes may contain abbreviations, typographical errors, mixed
languages, punctuation noise, component references, test measurements, and
status comments. A normalizer should link each supported defect mention to an
entry in the applicable controlled vocabulary. It should not invent a label
outside that vocabulary.

The product or codebook namespace is a hard constraint. Candidate entries from
an unrelated product family must not be used merely because their wording is
similar. Station applicability is also a constraint when the codebook declares
it: a candidate that cannot occur at the observed test stage should be rejected
or sent for review.

## Preserve source evidence

Keep the original record and retain exact source spans for traceability. A
reported span should be a verbatim substring of the source note; normalization,
translation, or spelling repair belongs in internal features and rationales,
not in the copied span.

Segment by defect mentions rather than by punctuation alone. Punctuation may
separate defects, but bilingual restatements can describe one defect and status
words can modify a preceding observation. Use component or location references,
fault terms, conjunctions, and codebook candidates together when deciding
whether text contains one mention or several.

## Candidate generation and ranking

A reusable pipeline can combine several independent signals:

1. Unicode and whitespace normalization for retrieval only;
2. exact matches on distinctive component, net, or test-item references;
3. token and character similarity against labels and keyword fields;
4. bilingual terminology or abbreviation expansion from a versioned lexicon;
5. product namespace and station-scope filtering;
6. comparison of the best candidate with plausible alternatives.

Do not use a single similarity score as proof of correctness. Strong decisions
normally have corroborating evidence, such as a compatible station plus a
shared fault term and a shared location reference. When evidence remains
ambiguous, emit the task's review/unknown representation rather than forcing a
code.

No universal fuzzy-match threshold or target unknown rate exists. Scorer
implementations, languages, codebook density, and deployment costs all affect
calibration. Select operating points from independently labeled deployment data
or an explicit review policy. If neither is available, expose the threshold as
a configuration parameter and retain the best/runner-up evidence for review.

## Adapt to data schemas by semantic role

Reusable normalizers should discover input roles from the supplied tables at
runtime instead of baking one dataset's header vocabulary into the program.
Infer roles from declared metadata, header meaning, value types, uniqueness,
and relationships between the event table and controlled vocabularies. Keep
the resolved role map as runtime state or explicit configuration, and fail with
an actionable ambiguity report when several columns plausibly serve the same
role. This separates a reusable normalization method from a particular export
schema without weakening required output fields.

## Confidence and rationale

Confidence should reflect empirical correctness likelihood, not cosmetic
precision. Calibrate it on held-out labeled records when possible. Useful
diagnostics include reliability diagrams, proper scoring rules, coverage at a
review threshold, and error rates by product, station, language, and defect
family.

Unknown or review decisions should generally carry less confidence than
well-supported code assignments, while still reflecting different degrees of
uncertainty. Avoid constant confidence values. A rationale should cite actual
source evidence and applicable codebook constraints without claiming evidence
that is absent from the record.

The decision and its confidence must remain coherent across the distribution,
not merely on average. Examine the lower tail of accepted assignments and the
upper tail of review/unknown assignments, stratified by relevant domains such
as product, station, language, or defect family. Large overlap is a signal to
revisit calibration or route weak accepted assignments to review. Do not repair
this by adding a constant to accepted scores: recompute confidence from the
same corroborating evidence used for the decision, check that stronger evidence
is monotonic with confidence, and choose any operating point from labeled
validation data or an explicit deployment cost policy rather than a universal
numeric cutoff.

## Runtime validation

Before saving output, check properties that follow from the instruction and the
current input:

- every input record is represented exactly as required;
- every non-unknown code and label comes from that record's product codebook;
- declared station constraints are satisfied;
- segment identifiers are unique and ordered within each record;
- every source span is non-empty and occurs verbatim in the source text;
- confidence values are numeric and within the declared range;
- unknown decisions use the required empty or sentinel fields;
- rationales are non-empty and cite observable evidence;
- output parses against the required schema.

Use synthetic examples and unit tests for tokenization, bilingual equivalence,
multi-defect segmentation, namespace isolation, station filtering, ambiguous
matches, and deterministic serialization. Derive all decisions for a real run
from the supplied logs and codebooks rather than storing current records in a
document or Skill.

## Public references

- NIST/SEMATECH discusses measurement-process variation and traceable process
  characterization: <https://www.itl.nist.gov/div898/handbook/mpc/mpc.htm>
- Unicode Standard Annex #15 defines Unicode normalization forms used during
  text preprocessing: <https://unicode.org/reports/tr15/>
- RapidFuzz documents similarity scorers and caller-selected cutoffs without
  prescribing a domain-wide decision threshold:
  <https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html>
