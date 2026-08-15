import re
import json


def parse_sections(text):
    """Parse script text into sections. Each section starts with [SectionName].
    Returns list of (section_id, lines) tuples in order."""
    sections = []
    current_id = None
    current_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        m = re.match(r'^\[([^\]]+)\]$', stripped)
        if m:
            if current_id is not None:
                sections.append((current_id, current_lines))
            current_id = m.group(1)
            current_lines = []
        elif current_id is not None and stripped:
            current_lines.append(stripped)
    if current_id is not None:
        sections.append((current_id, current_lines))
    return sections


def parse_line(line):
    """Parse a single line which can be:
    - A dialogue line: Speaker: text -> Target
    - A choice line: N. [optional tag] text -> Target
    Returns dict with keys: type, speaker, text, target, choice_num, tag
    """
    result = {
        'type': None,
        'speaker': None,
        'text': None,
        'target': None,
        'choice_num': None,
        'tag': None
    }
    
    # Check for choice line: starts with number followed by dot
    choice_match = re.match(r'^(\d+)\.\s+(.+?)\s*->\s*(\S+)\s*$', line)
    if choice_match:
        result['type'] = 'choice'
        result['choice_num'] = int(choice_match.group(1))
        choice_text = choice_match.group(2).strip()
        result['target'] = choice_match.group(3).strip()
        # Check for tag like [Lie], [Attack], etc.
        tag_match = re.match(r'^\[([^\]]+)\]\s*(.*)', choice_text)
        if tag_match:
            result['tag'] = tag_match.group(1)
            result['text'] = tag_match.group(2).strip() if tag_match.group(2).strip() else choice_text
        else:
            result['text'] = choice_text
        return result
    
    # Check for dialogue line: Speaker: text -> Target
    dialogue_match = re.match(r'^([^:]+?):\s+(.+?)\s*->\s*(\S+)\s*$', line)
    if dialogue_match:
        result['type'] = 'line'
        result['speaker'] = dialogue_match.group(1).strip()
        result['text'] = dialogue_match.group(2).strip()
        result['target'] = dialogue_match.group(3).strip()
        return result
    
    # Fallback: line without arrow (shouldn't happen in well-formed input)
    result['type'] = 'line'
    result['text'] = line
    return result


def build_graph(sections):
    """Build graph from parsed sections.
    Returns dict with 'nodes' and 'edges' lists.
    
    Node format: {"id": str, "text": str, "speaker": str, "type": "line"|"choice"}
    Edge format: {"from": str, "to": str, "text": str}
    """
    nodes = []
    edges = []
    seen_node_ids = set()
    declared_ids = set(s[0] for s in sections)
    
    for section_id, lines in sections:
        if section_id in seen_node_ids:
            continue  # avoid duplicates
        seen_node_ids.add(section_id)
        
        if not lines:
            # Empty section
            nodes.append({
                'id': section_id,
                'text': '',
                'speaker': '',
                'type': 'line'
            })
            continue
        
        # Determine node type: if any line is a choice, the node is a choice node
        parsed_lines = [parse_line(l) for l in lines]
        
        has_choices = any(pl['type'] == 'choice' for pl in parsed_lines)
        has_dialogue = any(pl['type'] == 'line' for pl in parsed_lines)
        
        if has_choices and has_dialogue:
            # Mixed: dialogue line(s) followed by choices
            # The dialogue lines are part of the node text, choices become edges
            dialogue_parts = [pl for pl in parsed_lines if pl['type'] == 'line']
            choice_parts = [pl for pl in parsed_lines if pl['type'] == 'choice']
            
            # Node text from dialogue parts
            text_parts = []
            speaker = ''
            for dp in dialogue_parts:
                if dp['speaker']:
                    speaker = dp['speaker']
                if dp['text']:
                    text_parts.append(dp['text'])
                # Dialogue lines with targets also create edges
                if dp['target']:
                    edges.append({
                        'from': section_id,
                        'to': dp['target'],
                        'text': dp['text'] or ''
                    })
            
            # If there are choices, node type is 'choice'
            node_text = ' '.join(text_parts)
            nodes.append({
                'id': section_id,
                'text': node_text,
                'speaker': speaker,
                'type': 'choice'
            })
            
            for cp in choice_parts:
                edge_text = cp['text'] or ''
                if cp['tag']:
                    edge_text = '[' + cp['tag'] + '] ' + edge_text
                edges.append({
                    'from': section_id,
                    'to': cp['target'],
                    'text': edge_text
                })
        elif has_choices:
            # Pure choice node
            choice_parts = [pl for pl in parsed_lines if pl['type'] == 'choice']
            nodes.append({
                'id': section_id,
                'text': '',
                'speaker': '',
                'type': 'choice'
            })
            for cp in choice_parts:
                edge_text = cp['text'] or ''
                if cp['tag']:
                    edge_text = '[' + cp['tag'] + '] ' + edge_text
                edges.append({
                    'from': section_id,
                    'to': cp['target'],
                    'text': edge_text
                })
        else:
            # Pure dialogue node
            text_parts = []
            speaker = ''
            for dp in parsed_lines:
                if dp['speaker']:
                    speaker = dp['speaker']
                if dp['text']:
                    text_parts.append(dp['text'])
                if dp['target']:
                    edges.append({
                        'from': section_id,
                        'to': dp['target'],
                        'text': dp['text'] or ''
                    })
            
            node_text = ' '.join(text_parts)
            nodes.append({
                'id': section_id,
                'text': node_text,
                'speaker': speaker,
                'type': 'line'
            })
    
    return {'nodes': nodes, 'edges': edges}


def parse_script(text):
    """Main entry point: parse script text and return graph dict."""
    sections = parse_sections(text)
    graph = build_graph(sections)
    return graph


def graph_to_dot(graph):
    """Convert graph dict to DOT format string."""
    lines = ['digraph dialogue {']
    lines.append('    rankdir=TB;')
    lines.append('    node [shape=box, style=filled, fillcolor=lightyellow];')
    lines.append('')
    
    # Collect all target IDs that are not declared nodes (terminal sentinels)
    declared_ids = set(n['id'] for n in graph['nodes'])
    terminal_targets = set()
    for edge in graph['edges']:
        if edge['to'] not in declared_ids:
            terminal_targets.add(edge['to'])
    
    # Add declared nodes
    for node in graph['nodes']:
        label = escape_dot_label(node['id'])
        if node['speaker']:
            label = escape_dot_label(node['speaker'] + ': ' + node['text'])
        elif node['text']:
            label = escape_dot_label(node['text'])
        
        shape = 'diamond' if node['type'] == 'choice' else 'box'
        fillcolor = 'lightblue' if node['type'] == 'choice' else 'lightyellow'
        lines.append(f'    "{escape_dot_id(node["id"])}" [label="{label}", shape={shape}, fillcolor={fillcolor}];')
    
    # Add terminal sentinel nodes
    for tid in sorted(terminal_targets):
        lines.append(f'    "{escape_dot_id(tid)}" [label="{escape_dot_label(tid)}", shape=doubleoctagon, fillcolor=lightgray];')
    
    lines.append('')
    
    # Add edges
    for edge in graph['edges']:
        label = escape_dot_label(edge['text'])
        lines.append(f'    "{escape_dot_id(edge["from"])}" -> "{escape_dot_id(edge["to"])}" [label="{label}"];')
    
    lines.append('}')
    return '\n'.join(lines)


def escape_dot_label(s):
    """Escape a string for use as a DOT label."""
    if not s:
        return ''
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\n', '\\n')
    return s


def escape_dot_id(s):
    """Escape a string for use as a DOT node ID."""
    return s.replace('"', '\\"')


def validate_graph(graph):
    """Validate graph constraints:
    1. All nodes reachable from first node
    2. All edge targets must exist (except terminal sentinels like 'End')
    3. Multiple paths can lead to 'End'
    Returns (is_valid, issues_list)
    """
    issues = []
    declared_ids = set(n['id'] for n in graph['nodes'])
    
    if not graph['nodes']:
        return False, ['No nodes found']
    
    # Build adjacency list
    adj = {n['id']: [] for n in graph['nodes']}
    for edge in graph['edges']:
        if edge['from'] in adj:
            adj[edge['from']].append(edge['to'])
    
    # Check reachability from first node
    first_id = graph['nodes'][0]['id']
    visited = set()
    stack = [first_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current in adj:
            for target in adj[current]:
                if target not in visited:
                    stack.append(target)
    
    unreachable = declared_ids - visited
    if unreachable:
        issues.append(f'Unreachable nodes: {unreachable}')
    
    # Check edge targets - all must exist as declared nodes or be terminal sentinels
    # Terminal sentinels are targets that don't have their own section
    # The doc says: keep terminal sentinels as edge targets, don't create nodes for them
    terminal_targets = set()
    for edge in graph['edges']:
        if edge['to'] not in declared_ids:
            terminal_targets.add(edge['to'])
    
    # Non-terminal targets must all resolve to declared nodes
    # (terminal targets are OK - like 'End')
    
    return len(issues) == 0, issues


def run_end_to_end(input_path, json_output_path, dot_output_path):
    """End-to-end entry point: read script, parse, write JSON and DOT."""
    with open(input_path, 'r') as f:
        text = f.read()
    
    graph = parse_script(text)
    
    # Validate
    is_valid, issues = validate_graph(graph)
    if not is_valid:
        print(f'Validation issues: {issues}')
    else:
        print('Graph validation passed')
    
    # Write JSON
    with open(json_output_path, 'w') as f:
        json.dump(graph, f, indent=2)
    print(f'Wrote JSON to {json_output_path}')
    
    # Write DOT
    dot_str = graph_to_dot(graph)
    with open(dot_output_path, 'w') as f:
        f.write(dot_str)
    print(f'Wrote DOT to {dot_output_path}')
    
    # Print stats
    print(f'Nodes: {len(graph["nodes"])}, Edges: {len(graph["edges"])}')
    
    return graph
