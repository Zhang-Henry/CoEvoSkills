# Dialogue Graph Basics

A branching dialogue can be represented as a directed graph: declared records
are nodes, and transitions are directed edges. Cycles and repeated references
to an existing node are normal.

A transition may also point to an external terminal sentinel. Unless that
sentinel has its own declared record, keep it as an edge target rather than
inventing a graph node for it. Reachability should be checked over the declared
nodes, while every nonterminal target should resolve to exactly one declared
node.

Parsers should discover record boundaries, identifiers, transition syntax,
terminal conventions, and the output schema from the supplied format. Preserve
source text, process the final record, avoid duplicate nodes, and escape labels
when serializing a visualization. No current identifiers, characters, counts,
or expected graph are specified here.
