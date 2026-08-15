# General Background for PDDL Airport Planning

This note summarizes public PDDL and airport-planning concepts. It does not describe any supplied instance, route, action sequence, object name, or installed solver.

## Domains, problems, and plans

A PDDL domain declares types, predicates, and action schemas. A problem declares objects, the initial state, and a goal. A plan is an ordered sequence of grounded actions whose preconditions hold when applied and whose cumulative effects make the goal true.

Classical PDDL uses a closed-world interpretation for ordinary predicates: facts absent from the state are false unless the domain models truth values through explicit predicates or other constructs. The domain file is authoritative; names that look similar can still represent distinct predicates or actions.

Plan interchange commonly represents each grounded action as a parenthesized expression with the action name followed by object arguments separated by whitespace. Tools can differ in accepted presentation syntax, so public instructions and the selected parser's documented format should be checked before writing output.

## Airport-domain reasoning

Airport ground-traffic domains model aircraft moving through a graph of runway, taxiway, and parking segments. Legal movement depends on more than topological adjacency. Direction, aircraft state, occupancy, and safety separation may all appear in preconditions, while effects can change location and release or establish constraints on nearby segments.

The exact graph and transition rules must be derived from action definitions in the supplied domain. Naming conventions are hints, not a substitute for parsing preconditions and effects. A transition that appears geometrically reversible may lack a reverse action or may require a different state.

With multiple aircraft, actions interact through shared resources and safety predicates. Solving one route independently can create a dead end for another aircraft, so the joint state and action ordering matter. Terminal actions such as parking or takeoff may be irreversible and should be delayed or committed only when their preconditions and downstream effects are understood.

## Solving and validation

Automated planning generally consists of parsing the domain and problem, grounding applicable actions, searching the state space, and validating the resulting sequence by replaying every action from the initial state. Solver support varies by PDDL requirement, so a parser accepting a file does not guarantee that a chosen search engine supports the domain.

For diagnosis, verify that every emitted action exists with the supplied arguments, each precondition holds at its step, every effect is applied consistently, and the final state satisfies every goal conjunct. Syntax-only checks cannot establish semantic validity. Concrete routes and plans must always be derived from the current domain and problem rather than from a reusable example.
