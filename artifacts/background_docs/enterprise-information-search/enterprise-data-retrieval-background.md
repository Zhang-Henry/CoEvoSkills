# General Enterprise Information Retrieval

Enterprise information retrieval combines structured records and unstructured text from heterogeneous systems. This document describes general retrieval principles only. The current dataset's products, identifiers, file layout, field names, source types, and answer mappings must be discovered from the supplied files at runtime.

## Schema discovery before retrieval

Exports from communication, document, meeting, code, and business systems do not share a universal schema. Even exports from the same vendor can differ by version or organization.

A robust workflow begins by inventorying files and sampling their structures. For each source, determine:

- the serialization format and character encoding;
- top-level container types and nested keys;
- which fields are identifiers, display labels, timestamps, text, or links;
- whether records are embedded, referenced, or split across files; and
- whether names, identifiers, and dates use consistent representations.

Do not import a field path, codename mapping, directory count, or capitalization convention from an example. Derive it from repeated evidence in the current data.

## Identity resolution

The same person may appear as an internal identifier in one source, a display name in another, and an email-like address elsewhere. Resolve identities by building a mapping from authoritative metadata and corroborating contextual evidence.

Names alone may be ambiguous. Prefer stable identifiers when they exist, and use role, team, participants, authorship metadata, or nearby activity only as disambiguating evidence. Keep an evidence trail for each resolved identity rather than silently merging similar names.

## Authorship, participation, and contribution

Authorship, attendance, mention, review, and substantive contribution are different relations. A person who attended a meeting or appeared near a document link is not necessarily a reviewer. Conversely, useful feedback may occur outside the formal document record.

Interpret the wording of each question first. Then collect only records that directly support the requested relation, such as explicit authorship metadata, a review statement, proposed changes, analytical feedback, or a clearly attributed action. Deduplicate only after preserving the evidence behind each attribution. The set of sources to combine should be determined by available evidence, not by a fixed union recipe.

A useful guard against over-inclusive answers is a candidate-to-evidence ledger. For every candidate, record the source, the exact attributed action, the entity that action concerns, and the time or version context. Apply the same question-derived predicate to every row, and exclude candidates supported only by co-occurrence, team membership, attendance, acknowledgement, or discussion of a different entity. This is a semantic verification method, not a rule about how many candidates an answer should contain.

## Temporal and version reasoning

Documents and discussions evolve. Creation, revision, publication, review, and closure timestamps can refer to different events. Associate evidence with the relevant version and use the time semantics stated by the question or represented by the source. Do not assume a fixed review window.

Normalize timestamps only after detecting their timezone and precision. When ordering events from multiple systems, account for missing timezone information and source-specific clock conventions.

## Links and resource classification

Links may be represented as plain URLs, markup, rich objects, or references into another table. Inspect the actual representation before searching or deduplicating them. Parse URLs structurally when classifying hostnames, paths, or query parameters.

Whether a resource is internal, external, a demonstration, documentation, or another artifact should be supported by its domain, metadata, description, and surrounding context. Organization-specific domains and resource categories must be inferred from the supplied evidence rather than assumed.

## Efficient search over large exports

Useful general techniques include:

1. Parse the question into entities, relations, time constraints, and required output types.
2. Build a lightweight index of filenames, identifiers, labels, timestamps, and searchable text.
3. Use exact identifiers first, then aliases and normalized text where needed.
4. Narrow candidate records before reading long documents or transcripts.
5. Follow cross-references only when they contribute evidence to the requested relation.
6. Retain provenance so each answer item can be traced to one or more records.

Programmatic filtering is usually more reliable than loading an entire repository into a language-model context. Search should still allow semantic variants rather than relying on one exact phrase.

## Verification

Before writing an answer:

- reread the question and confirm that each item has the requested semantic role;
- distinguish identifiers from record IDs, labels, and display names using the discovered schema;
- check duplicates and conflicting evidence;
- verify time and version constraints;
- validate that collection and scalar shapes follow the task instruction; and
- serialize the final object with valid JSON types.

JSON strings, numbers, booleans, arrays, and objects are not interchangeable merely because their printed forms look similar. Preserve the semantic type of each value: measurements and counts are normally JSON numbers, identifiers are normally strings, and requested collections remain arrays even when they contain one item. Placeholder text in a format illustration does not by itself convert a numeric measurement into text; use the surrounding prose and discovered schema to determine the type.

No current-dataset answer, reviewer list, product mapping, schema path, or hidden output convention is supplied by this background.
