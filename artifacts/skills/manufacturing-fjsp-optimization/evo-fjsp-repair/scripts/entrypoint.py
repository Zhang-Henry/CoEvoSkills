"""
End-to-end entry point for FJSP baseline repair.
"""
import sys
import os

# Ensure scripts dir is on path
scripts_dir = os.path.dirname(os.path.abspath(__file__))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from parser import parse_instance, parse_downtime, parse_policy, parse_baseline
from constraints import validate_schedule, compute_policy_metrics
from solver import repair_baseline_strategy, try_alternative_schedules
from writer import write_solution_json, write_schedule_csv


def run(data_dir, output_dir):
    """Run the full FJSP repair pipeline.
    
    Args:
        data_dir: directory containing instance.txt, downtime.csv, policy.json, baseline_solution.json
        output_dir: directory to write solution.json and schedule.csv
    
    Returns:
        dict with 'schedule', 'makespan', 'issues', 'metrics'
    """
    # Parse inputs
    num_jobs, num_machines, jobs = parse_instance(os.path.join(data_dir, 'instance.txt'))
    downtimes = parse_downtime(os.path.join(data_dir, 'downtime.csv'))
    policy = parse_policy(os.path.join(data_dir, 'policy.json'))
    _, bl_makespan, baseline_schedule = parse_baseline(os.path.join(data_dir, 'baseline_solution.json'))
    
    print(f"Instance: {num_jobs} jobs, {num_machines} machines")
    print(f"Baseline makespan: {bl_makespan}")
    print(f"Downtime windows: {downtimes}")
    
    # Check baseline violations
    bl_issues = validate_schedule(baseline_schedule, jobs, downtimes, policy, baseline_schedule)
    print(f"Baseline issues: {bl_issues}")
    
    # Try repair strategies
    schedule = try_alternative_schedules(jobs, downtimes, policy, baseline_schedule)
    
    # Validate
    issues = validate_schedule(schedule, jobs, downtimes, policy, baseline_schedule)
    makespan = max(op['end'] for op in schedule)
    mc, l1 = compute_policy_metrics(schedule, baseline_schedule)
    
    print(f"\nRepaired schedule:")
    for op in sorted(schedule, key=lambda x: (x['start'], x['job'], x['op'])):
        print(f"  Job {op['job']} Op {op['op']}: machine {op['machine']}, [{op['start']}, {op['end']}), dur={op['dur']}")
    print(f"Makespan: {makespan}")
    print(f"Machine changes: {mc}, L1 shift: {l1}")
    print(f"Issues: {issues}")
    
    # Write outputs
    write_solution_json(schedule, os.path.join(output_dir, 'solution.json'))
    write_schedule_csv(schedule, os.path.join(output_dir, 'schedule.csv'))
    
    print(f"\nOutputs written to {output_dir}")
    
    return {
        'schedule': schedule,
        'makespan': makespan,
        'issues': issues,
        'metrics': {'machine_changes': mc, 'l1_shift': l1}
    }


def validate(output_dir, data_dir):
    """Validate the generated outputs."""
    import json
    import csv
    
    num_jobs, num_machines, jobs = parse_instance(os.path.join(data_dir, 'instance.txt'))
    downtimes = parse_downtime(os.path.join(data_dir, 'downtime.csv'))
    policy = parse_policy(os.path.join(data_dir, 'policy.json'))
    _, _, baseline_schedule = parse_baseline(os.path.join(data_dir, 'baseline_solution.json'))
    
    # Read solution.json
    with open(os.path.join(output_dir, 'solution.json')) as f:
        solution = json.load(f)
    
    schedule = solution['schedule']
    reported_makespan = solution['makespan']
    actual_makespan = max(op['end'] for op in schedule)
    
    # Read schedule.csv
    with open(os.path.join(output_dir, 'schedule.csv')) as f:
        reader = csv.DictReader(f)
        csv_rows = []
        for row in reader:
            csv_rows.append({
                'job': int(row['job']),
                'op': int(row['op']),
                'machine': int(row['machine']),
                'start': int(row['start']),
                'end': int(row['end']),
                'dur': int(row['dur'])
            })
    
    # Check JSON-CSV consistency
    json_set = set()
    for op in schedule:
        json_set.add((op['job'], op['op'], op['machine'], op['start'], op['end'], op['dur']))
    csv_set = set()
    for op in csv_rows:
        csv_set.add((op['job'], op['op'], op['machine'], op['start'], op['end'], op['dur']))
    
    errors = []
    if json_set != csv_set:
        errors.append("JSON and CSV data mismatch")
    if reported_makespan != actual_makespan:
        errors.append(f"Reported makespan {reported_makespan} != actual {actual_makespan}")
    if not solution.get('status'):
        errors.append("Missing status field")
    
    issues = validate_schedule(schedule, jobs, downtimes, policy, baseline_schedule)
    if issues:
        errors.append(f"Schedule validation issues: {issues}")
    
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print("VALIDATION PASSED")
    print(f"  Makespan: {actual_makespan}")
    mc, l1 = compute_policy_metrics(schedule, baseline_schedule)
    print(f"  Machine changes: {mc}, L1 shift: {l1}")
    return True


if __name__ == '__main__':
    data_dir = sys.argv[1] if len(sys.argv) > 1 else '/app/data'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else '/app/output'
    result = run(data_dir, output_dir)
    if result['issues']:
        print("\nWARNING: Schedule has issues!")
        sys.exit(1)
    validate(output_dir, data_dir)
