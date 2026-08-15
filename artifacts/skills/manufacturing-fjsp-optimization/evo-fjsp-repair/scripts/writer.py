import json
import csv
import os


def write_solution_json(schedule, output_path):
    """Write schedule to solution.json format."""
    makespan = max(op['end'] for op in schedule)
    solution = {
        "status": "REPAIRED",
        "makespan": makespan,
        "schedule": sorted(schedule, key=lambda x: (x['start'], x['job'], x['op']))
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(solution, f, indent=2)
    return solution


def write_schedule_csv(schedule, output_path):
    """Write schedule to CSV format."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sorted_sched = sorted(schedule, key=lambda x: (x['start'], x['job'], x['op']))
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['job', 'op', 'machine', 'start', 'end', 'dur'])
        writer.writeheader()
        for op in sorted_sched:
            writer.writerow({
                'job': op['job'],
                'op': op['op'],
                'machine': op['machine'],
                'start': op['start'],
                'end': op['end'],
                'dur': op['dur']
            })
