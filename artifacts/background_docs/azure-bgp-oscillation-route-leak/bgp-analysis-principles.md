# BGP policy analysis principles

A routing preference system can be represented as a directed graph: an edge
records that one routing domain currently prefers a route through another.
A persistent oscillation requires a preference dependency cycle. Analyze the
runtime topology and policies to identify the actual cycle; do not infer one
from names or from a generic description of a mechanism.

Under the common valley-free model, customer-learned routes may be exported to
any neighbor, while peer- or provider-learned routes are normally exported only
to customers. Check every runtime advertisement by combining the relationship
on which the route was learned with the relationship on which it is exported.

Evaluate a proposed intervention by applying its stated effects to a copy of
the runtime preference and advertisement graphs, then repeat both analyses. A
change resolves a control-plane problem only when the relevant cycle or invalid
export is absent after the change. Operational side effects, monitoring, and
forwarding overrides should be reported according to what they actually alter;
their labels alone are not evidence that a routing policy defect was removed.
