"""Utility functions for PDDL airport planning tasks."""
import re
import json
import os


def load_tasks(problem_json_path):
    """Load task definitions from problem.json.
    
    Args:
        problem_json_path: Path to the problem.json file
    
    Returns:
        List of task dicts with keys: id, domain, problem, plan_output
    """
    with open(problem_json_path) as f:
        return json.load(f)


def solve_pddl_task(domain_path, problem_path):
    """Solve a PDDL planning task using pyperplan directly.
    
    Uses pyperplan's native parser and BFS search to find a plan.
    Returns the plan as a list of operator name strings in standard
    PDDL format: (action_name arg1 arg2 ...)
    
    Args:
        domain_path: Path to the PDDL domain file
        problem_path: Path to the PDDL problem file
    
    Returns:
        List of action strings in PDDL format, or None if no plan found
    """
    from pyperplan.planner import _parse, _ground
    from pyperplan.search import breadth_first_search
    
    problem = _parse(domain_path, problem_path)
    task = _ground(problem)
    
    solution = breadth_first_search(task)
    
    if solution:
        return [op.name for op in solution]
    else:
        return None


def solve_pddl_task_with_heuristic(domain_path, problem_path):
    """Solve a PDDL planning task using pyperplan with hFF heuristic.
    
    Falls back to BFS if heuristic search fails.
    
    Args:
        domain_path: Path to the PDDL domain file
        problem_path: Path to the PDDL problem file
    
    Returns:
        List of action strings in PDDL format, or None if no plan found
    """
    from pyperplan.planner import _parse, _ground
    from pyperplan.search import astar_search, breadth_first_search
    
    problem = _parse(domain_path, problem_path)
    task = _ground(problem)
    
    # Try heuristic search first
    try:
        from pyperplan.heuristics.hff import hFFHeuristic
        heuristic = hFFHeuristic(task)
        solution = astar_search(task, heuristic)
        if solution:
            return [op.name for op in solution]
    except Exception:
        pass
    
    # Fallback to BFS
    solution = breadth_first_search(task)
    if solution:
        return [op.name for op in solution]
    
    return None


def write_plan(actions, output_path):
    """Write a list of plan actions to a file.
    
    Each action is written on its own line.
    
    Args:
        actions: List of action strings
        output_path: Path to write the plan file
    """
    outdir = os.path.dirname(output_path)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    with open(output_path, 'w') as f:
        for action in actions:
            f.write(action + '\n')


def solve_and_write(domain_path, problem_path, output_path):
    """Solve a PDDL task and write the plan to a file.
    
    Args:
        domain_path: Path to the PDDL domain file
        problem_path: Path to the PDDL problem file
        output_path: Path to write the plan file
    
    Returns:
        True if plan found and written, False otherwise
    """
    actions = solve_pddl_task_with_heuristic(domain_path, problem_path)
    if actions:
        write_plan(actions, output_path)
        return True
    return False
