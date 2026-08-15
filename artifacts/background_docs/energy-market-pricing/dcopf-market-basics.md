# DC optimal power flow with reserve co-optimization

A lossless DC-OPF represents bus-angle differences, branch reactance, nodal
power balance, generator limits, and thermal flow limits in one consistent
indexing convention.  MATPOWER identifiers need not equal array positions, so
build explicit maps from external bus identifiers to optimization indices.

Energy and spinning reserve should be co-optimized.  Standard capacity
coupling limits scheduled energy plus upward reserve by the generator's
available capability, while the system reserve requirement couples all reserve
offers.  Locational marginal prices and the reserve clearing price are dual
values whose sign depends on the exact constraint convention; verify them by
small perturbations of the corresponding right-hand sides.

For a transmission counterfactual, clone the parsed model, change only the
declared branch capacity, and solve both cases with identical conventions.
Identify binding constraints using the declared tolerance and validate nodal
balance, generator capability, reserve feasibility, branch flows, objective
reconstruction, and scenario differencing before reporting results.

