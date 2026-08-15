"""End-to-end entry point for solving PDDL airport planning tasks."""
import sys
import json
import os


def solve_all_tasks(problem_json_path, base_dir=None):
    """Solve all PDDL planning tasks specified in problem.json.
    
    Args:
        problem_json_path: Path to the problem.json file
        base_dir: Base directory for resolving relative paths.
                  Defaults to the directory containing problem.json.
    
    Returns:
        Dict mapping task IDs to success/failure status
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from utils import load_tasks, solve_and_write
    
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(problem_json_path))
    
    tasks = load_tasks(problem_json_path)
    results = {}
    
    for task in tasks:
        task_id = task['id']
        domain_path = os.path.join(base_dir, task['domain'])
        problem_path = os.path.join(base_dir, task['problem'])
        output_path = os.path.join(base_dir, task['plan_output'])
        
        print(f"Solving {task_id}...")
        print(f"  Domain: {domain_path}")
        print(f"  Problem: {problem_path}")
        print(f"  Output: {output_path}")
        
        try:
            success = solve_and_write(domain_path, problem_path, output_path)
            if success:
                print(f"  -> Plan found and written")
                with open(output_path) as f:
                    print(f"  Plan:\n{f.read()}")
            else:
                print(f"  -> No plan found!")
            results[task_id] = success
        except Exception as e:
            print(f"  -> Error: {e}")
            import traceback
            traceback.print_exc()
            results[task_id] = False
    
    return results


def validate_plans(problem_json_path, base_dir=None):
    """Validate that all plan output files exist and are non-empty.
    
    Args:
        problem_json_path: Path to the problem.json file
        base_dir: Base directory for resolving relative paths.
    
    Returns:
        True if all plans exist and are non-empty, False otherwise
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(problem_json_path))
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from utils import load_tasks
    
    tasks = load_tasks(problem_json_path)
    all_valid = True
    
    for task in tasks:
        output_path = os.path.join(base_dir, task['plan_output'])
        if not os.path.exists(output_path):
            print(f"FAIL: {task['id']} - output file missing: {output_path}")
            all_valid = False
            continue
        
        with open(output_path) as f:
            content = f.read().strip()
        
        if not content:
            print(f"FAIL: {task['id']} - output file is empty")
            all_valid = False
            continue
        
        lines = [l for l in content.split('\n') if l.strip()]
        print(f"OK: {task['id']} - {len(lines)} actions")
        
        # Check each line looks like a valid PDDL action: (action_name args...)
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            if not (line.startswith('(') and line.endswith(')')):
                print(f"  WARNING: line {i+1} may not be valid PDDL format: {line}")
    
    return all_valid


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python solve.py <problem.json> [base_dir]")
        sys.exit(1)
    
    problem_json = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else None
    
    results = solve_all_tasks(problem_json, base)
    
    print("\n=== Validation ===")
    valid = validate_plans(problem_json, base)
    
    if all(results.values()) and valid:
        print("\nAll tasks solved and validated successfully!")
    else:
        print("\nSome tasks failed!")
        sys.exit(1)
