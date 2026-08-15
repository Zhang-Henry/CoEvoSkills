# DC dispatch and reserve validation principles

Parse a power-system case into an explicit internal model before optimization.
Bus identifiers are labels rather than guaranteed row positions.  Respect
equipment status, generator bounds, branch ratings, transformer taps and phase
shifts, the selected reference bus, units, and every declared cost-model type.

In a lossless DC model, branch flows follow voltage-angle differences and
reactance, while each bus must balance generation, demand, and incident flow.
Absolute angle is fixed at the reference bus.  Reserve is a separate decision
that shares physical generator capacity with energy; add only the reserve
products, eligibility rules, and requirements supported by the supplied data
and instruction.

Use a solver appropriate to the resulting linear or convex-quadratic problem.
A successful status alone does not establish correctness.  Recompute nodal
residuals, flows, equipment bounds, reserve coupling, system totals, and the
objective from the returned variables.  For ranking or optimality-sensitive
outputs, use unrounded values and cross-check the objective with an independent
calculation or a small alternative solve.

Derive output fields from the task contract and runtime identifiers.  Preserve
the source case, avoid benchmark-specific defaults for absent extensions, and
round only when serializing the final report.

