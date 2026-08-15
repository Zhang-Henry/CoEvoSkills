---
name: evo-dialogue-parser
description: "Parse branching dialogue scripts into structured JSON graphs and DOT visualizations. Use when given a text file with section headers containing dialogue lines and numbered choices."
---

# Dialogue Parser Skill

Parses branching dialogue scripts into structured JSON graphs with nodes and edges,
plus DOT format visualization.

## Input Format

Sections delimited by `[SectionName]` containing:
- Dialogue lines: `Speaker: text -> Target`
- Choice lines: `N. [optional tag] text -> Target`

## Output Format

### JSON (`dialogue.json`)
```json
{
  "nodes": [{"id": "...", "text": "...", "speaker": "...", "type": "line|choice"}],
  "edges": [{"from": "...", "to": "...", "text": "..."}]
}
```

### DOT (`dialogue.dot`)
Graphviz DOT format for visualization.

## Key Rules

1. Terminal sentinels (like "End") that have no declared section are NOT added as nodes
2. All declared nodes must be reachable from the first node
3. All non-terminal edge targets must resolve to declared nodes
4. Node type is "choice" if the section contains numbered choices, "line" otherwise
5. For choice nodes, each choice becomes an edge; for line nodes, the arrow target becomes an edge
6. Tags in choices like `[Lie]` are preserved in edge text

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dialogue-parser/scripts')
from utils import run_end_to_end, parse_script, validate_graph

# End-to-end: parse script and write outputs
graph = run_end_to_end('/app/script.txt', '/app/dialogue.json', '/app/dialogue.dot')

# Validate
is_valid, issues = validate_graph(graph)
assert is_valid, f"Validation failed: {issues}"
print("All validations passed")
```

## Functions

- `parse_sections(text)` - Split text into (section_id, lines) tuples
- `parse_line(line)` - Parse a single dialogue or choice line
- `build_graph(sections)` - Build nodes/edges from parsed sections
- `parse_script(text)` - Main parser: text -> graph dict
- `graph_to_dot(graph)` - Convert graph to DOT string
- `validate_graph(graph)` - Check reachability and edge target constraints
- `run_end_to_end(input_path, json_path, dot_path)` - Full pipeline
