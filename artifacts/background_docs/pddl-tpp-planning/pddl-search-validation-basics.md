# PDDL search and plan validation basics

A PDDL plan is a sequence of grounded actions whose preconditions hold in the
state reached by all earlier actions. Parse the supplied domain and problem at
runtime, including typed objects, predicates, initial facts, goals, action
parameters, preconditions, and effects. Do not assume that names or action
signatures transfer between problem instances.

Ground only type-compatible actions. State-space search may use breadth-first,
uniform-cost, or heuristic methods depending on the action costs and problem
size. Track visited states with a canonical representation, retain predecessor
actions for plan reconstruction, and avoid pruning a state unless the chosen
search algorithm makes that pruning sound.

Independently replay every proposed action from the declared initial state.
Check parameter count and types, positive and negative preconditions, add and
delete effects, and the complete goal after the final action. Serialize only
the grounded action sequence in the syntax requested by the caller, preserving
the domain's exact action and object names.
