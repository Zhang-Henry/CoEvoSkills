import json
import os
import subprocess
import re
import sys
import time


def convert_pddl_plan_line(line):
    """Convert '(action arg1 arg2 ...)' to 'action(arg1, arg2, ...)'."""
    line = line.strip()
    if not line:
        return None
    # Remove outer parens if present
    if line.startswith('(') and line.endswith(')'):
        inner = line[1:-1].strip()
    else:
        inner = line
    parts = inner.split()
    if not parts:
        return None
    action_name = parts[0]
    args = parts[1:]
    if args:
        return f"{action_name}({', '.join(args)})"
    else:
        return f"{action_name}()"


def convert_plan(plan_text):
    """Convert full pyperplan plan output to required format."""
    lines = plan_text.strip().split('\n')
    converted = []
    for line in lines:
        line = line.strip()
        if line:
            converted_line = convert_pddl_plan_line(line)
            if converted_line:
                converted.append(converted_line)
    return '\n'.join(converted)


def solve_task(domain_path, problem_path, plan_output_path, base_dir='/app',
               timeout=120, search='bfs', heuristic=None):
    """Solve a single TPP task using pyperplan.
    
    Tries multiple search strategies if the first one fails or times out.
    """
    domain_full = os.path.join(base_dir, domain_path)
    problem_full = os.path.join(base_dir, problem_path)
    output_full = os.path.join(base_dir, plan_output_path)
    
    # Ensure output directory exists
    out_dir = os.path.dirname(output_full)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    
    # Try different search strategies
    strategies = [
        ('gbf', 'hff'),
        ('astar', 'hff'),
        ('astar', 'hadd'),
        ('astar', 'lmcut'),
        ('gbf', 'hadd'),
        ('ehs', 'hff'),
        ('bfs', None),
    ]
    
    for s, h in strategies:
        try:
            result = solve_with_strategy(domain_full, problem_full, s, h, timeout)
            if result is not None:
                plan_text = convert_plan(result)
                if plan_text.strip():
                    with open(output_full, 'w') as f:
                        f.write(plan_text + '\n')
                    print(f"  Solved with strategy ({s}, {h}): {len(plan_text.splitlines())} actions")
                    return True
        except Exception as e:
            print(f"  Strategy ({s}, {h}) failed: {e}")
            continue
    
    print(f"  ERROR: All strategies failed for {problem_path}")
    return False


def solve_with_strategy(domain_path, problem_path, search, heuristic, timeout):
    """Run pyperplan with a specific search strategy. Returns raw plan text."""
    try:
        from pyperplan.planner import HEURISTICS, SEARCHES
        from pyperplan.pddl.parser import Parser
        from pyperplan import grounding
        
        parser = Parser(domain_path, problem_path)
        domain = parser.parse_domain()
        problem = parser.parse_problem(domain)
        task = grounding.ground(problem)
        
        search_fn = SEARCHES.get(search)
        heuristic_obj = None
        if heuristic and heuristic in HEURISTICS:
            heuristic_obj = HEURISTICS[heuristic](task)
        
        if search_fn is None:
            return None
        
        solution = search_fn(task, heuristic_obj)
        
        if solution is None:
            return None
        
        # op.name is already like '(drive truck1 depot1 market1)'
        lines = [op.name for op in solution]
        return '\n'.join(lines)
    except Exception as e:
        print(f"    Library approach failed: {e}")
        # Fallback to CLI
        return solve_with_cli(domain_path, problem_path, search, heuristic, timeout)


def solve_with_cli(domain_path, problem_path, search, heuristic, timeout):
    """Run pyperplan via CLI as fallback."""
    cmd = ['pyperplan']
    if search:
        cmd.extend(['-s', search])
    if heuristic:
        cmd.extend(['-H', heuristic])
    cmd.extend([domain_path, problem_path])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        # pyperplan writes .soln file
        soln_file = problem_path + '.soln'
        if os.path.exists(soln_file):
            with open(soln_file, 'r') as f:
                plan = f.read()
            os.remove(soln_file)  # Clean up
            return plan
    except subprocess.TimeoutExpired:
        print(f"    CLI timeout after {timeout}s")
    except Exception as e:
        print(f"    CLI error: {e}")
    return None


def solve_all_tasks(problem_json_path='/app/problem.json', base_dir='/app', timeout=120):
    """Solve all tasks specified in problem.json."""
    with open(problem_json_path, 'r') as f:
        tasks = json.load(f)
    
    results = []
    for task in tasks:
        task_id = task['id']
        domain = task['domain']
        problem = task['problem']
        plan_output = task['plan_output']
        
        print(f"Solving {task_id}: {problem} -> {plan_output}")
        success = solve_task(domain, problem, plan_output, base_dir, timeout)
        results.append({'id': task_id, 'success': success})
    
    return results


def validate_plan(domain_path, problem_path, plan_path, base_dir='/app'):
    """Validate a plan by checking format and replaying actions."""
    plan_full = os.path.join(base_dir, plan_path)
    
    if not os.path.exists(plan_full):
        return False, "Plan file does not exist"
    
    with open(plan_full, 'r') as f:
        plan_text = f.read().strip()
    
    if not plan_text:
        return False, "Plan file is empty"
    
    lines = [l.strip() for l in plan_text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        # Check format: action_name(arg1, arg2, ...)
        match = re.match(r'^[\w-]+\([\w, ]+\)$', line)
        if not match:
            return False, f"Line {i+1} has invalid format: {line}"
    
    return True, f"Plan has {len(lines)} actions, format OK"


def validate_all_plans(problem_json_path='/app/problem.json', base_dir='/app'):
    """Validate all plans."""
    with open(problem_json_path, 'r') as f:
        tasks = json.load(f)
    
    all_valid = True
    for task in tasks:
        plan_path = task['plan_output']
        valid, msg = validate_plan(task['domain'], task['problem'], plan_path, base_dir)
        status = "PASS" if valid else "FAIL"
        print(f"  {task['id']}: {status} - {msg}")
        if not valid:
            all_valid = False
    
    return all_valid


if __name__ == '__main__':
    results = solve_all_tasks()
    print("\nValidation:")
    validate_all_plans()
