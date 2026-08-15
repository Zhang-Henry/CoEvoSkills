# Interpreting Wyckoff-position summaries

A symmetry analyzer can expose both the original parsed structure and a
standardized setting.  Keep those coordinate systems distinct.  When a result
requests a representative atom from the supplied structure, map the symmetry
orbit back to the corresponding original site and use the first occurrence in
the requested ordering.  Standardized-cell coordinates are appropriate only
when the output contract explicitly asks for that setting.

A Wyckoff symbol combines an orbit multiplicity with a letter, and distinct
inequivalent orbits can share the same letter.  If an output schema has only one
entry per letter, do not silently discard later orbits: apply an explicit
letter-level reduction, such as summing the represented-site multiplicities,
while retaining the first requested representative coordinate.  Validate the
reduction by reconciling the represented-site total with the parsed structure.

Fractional coordinates are periodic, so zero and one describe equivalent
positions physically, but a serialized answer may preserve the source
representative.  Perform bounded-denominator approximation on the selected
source coordinate and preserve an endpoint representation when the contract
asks for that atom's approximate coordinates; apply modulo canonicalization
only when a canonical half-open interval is explicitly required.

For every input, verify that all orbit occurrences contributed to the summary,
that representative coordinates came from the intended setting and ordering,
and that every emitted coordinate is a deterministic rational string within
the requested denominator bound.
