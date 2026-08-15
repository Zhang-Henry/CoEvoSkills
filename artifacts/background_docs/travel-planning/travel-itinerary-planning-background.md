# Database-Grounded Travel Itinerary Planning

This document describes general techniques for constructing an itinerary from structured travel data. It does not specify any current origin, destination, dates, trip length, route, property, venue, cuisine combination, database schema, tool identifier, output layout, or expected answer. Those details must be read from the supplied instruction and discovered from the available data interfaces.

## Treat Planning as Constraint Satisfaction

Translate the travel request into explicit constraints before choosing any records. Common categories include:

- geography: permitted regions, starting point, required coverage, and route endpoints;
- time: dates, number of days, overnight transitions, and visit duration;
- party needs: capacity, accessibility, or lodging policies;
- transport: allowed modes and feasible travel times;
- budget: total and category-specific limits;
- preferences: cuisines, activities, lodging type, or pace; and
- output contract: required serialization, fields, and destination path.

Separate hard constraints from preferences. Reject candidates that violate hard constraints, then use preferences to rank the feasible set. When wording is ambiguous, document a defensible interpretation rather than inventing a hidden rule.

## Discover the Available Data

Structured travel datasets vary widely. Inspect the provided search interfaces, data dictionaries, and files before writing queries. Determine which attributes represent location, price and units, capacity, policies, categories, ratings, travel duration, and record identity. Do not assume fixed column names, value encodings, or file layouts.

Preserve the source spelling of selected entities so that results remain traceable to actual records. If joining across sources, normalize only what is necessary for matching, retain the original value for output, and check for ambiguous place names.

Record absence has limited meaning. A missing price, policy, route, or category is not proof that a constraint is satisfied. Treat unknown information separately from an explicit positive or negative value, according to the task's required certainty.

## Generate and Filter Candidates

Build candidates from the supplied data rather than memory:

1. identify destinations that satisfy the geographic request;
2. find lodging candidates for the relevant overnight locations;
3. find meal and activity candidates for each visit location;
4. find transport links between consecutive locations; and
5. retain source evidence for every selected record.

Policy text may require semantic interpretation. Negated restrictions, positive permissions, and missing statements are different states. Capacity should be checked against the full party, and any minimum-stay condition should be checked against the planned number of nights.

For restaurants or activities with multiple categories, parse the supplied category representation and compare normalized category labels. Do not infer a category from an establishment's name. Coverage preferences should be checked across the completed itinerary, while location consistency should be checked for each individual entry.

## Route and Schedule Construction

Choose a city sequence only after checking that consecutive transport legs are represented and feasible. A distance matrix may be directional or incomplete, so validate the requested direction of each leg instead of assuming symmetry.

Account for travel time on transition days. Meals, activities, current location, transportation, and overnight location should tell a coherent temporal story. Avoid impossible combinations such as scheduling a full day of activities before a long departure or assigning lodging in a place the route never reaches.

Whether the starting point counts as a visited destination, and whether the route must return to it, depends on the instruction. Do not impose either convention silently.

## Budget Accounting

Define a cost ledger from the quantities actually available in the data. Typical components can include lodging by night, meals by party size, and transport by leg. Confirm currencies, units, and whether quoted prices are per person, per room, per meal, or per trip.

Sum costs without double-counting transition days or overnight stays. Keep unknown costs visible rather than treating them as zero. If the task permits estimates, state the estimation rule and retain a reserve below the budget ceiling for uncertain expenses.

## Produce the Required Output

Follow the output schema and formatting stated in the current instruction exactly; do not derive an output layout from this background. Use only entities supported by the provided database, keep day ordering and route transitions internally consistent, and report data operations truthfully. Do not claim that an operation was performed when it was not.

Before saving, validate the output mechanically where possible:

- required keys and types match the instruction;
- the number and ordering of schedule entries are correct;
- every named entity resolves to a source record in the appropriate location;
- every hard constraint is satisfied on every applicable day or night;
- preferences have measurable coverage across the trip;
- every route leg exists in the allowed transport data;
- the cost ledger remains within the stated budget; and
- the serialized file parses successfully at the required path.

## Keep Evidence Separate from Decisions

A robust planner keeps a small provenance record for each decision: the constraint being satisfied, the source record used, and any interpretation applied. This makes errors easier to diagnose and prevents a plausible-sounding itinerary from drifting away from the supplied database. The final itinerary may be concise, but its entries should remain reproducible from the available data.
