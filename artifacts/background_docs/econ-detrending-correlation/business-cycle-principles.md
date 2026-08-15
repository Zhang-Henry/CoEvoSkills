# Business-cycle measurement principles

Nominal series combine quantities and prices. Convert them to the requested
real measure with the specified price index, align observations by their actual
period labels, and do not silently substitute a different source or frequency.

Trend-cycle decompositions are sensitive to transformation, data frequency,
smoothing choice, sample boundaries, and missing periods. Treat those choices
as part of the analysis contract: obtain them from the task, supplied data, or
the cited public method, and record them with the result. Do not infer them from
spreadsheet coordinates or from a convenient library default.

Parse mixed annual, quarterly, footnote, and subtotal rows by their semantics.
After producing the two cyclical series, verify their aligned sample and compute
the requested association on that common sample. Recalculate representative
intermediate values independently before final delivery.
