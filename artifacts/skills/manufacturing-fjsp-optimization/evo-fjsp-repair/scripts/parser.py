import json
import csv
import os

def parse_instance(filepath):
    """Parse FJSP instance file (multi-line format).
    Format:
      Line 1: num_jobs num_machines
      For each job:
        Line: num_operations
        For each operation:
          Line: num_eligible m1 d1 m2 d2 ...
    Returns: (num_jobs, num_machines, jobs)
    jobs[j][o] = list of (machine_id, duration) tuples
    """
    with open(filepath) as f:
        lines = [l.strip() for l in f if l.strip()]
    
    first_line = lines[0].split()
    num_jobs = int(first_line[0])
    num_machines = int(first_line[1])
    
    jobs = []
    line_idx = 1
    for j in range(num_jobs):
        num_ops = int(lines[line_idx].strip())
        line_idx += 1
        ops = []
        for o in range(num_ops):
            parts = list(map(int, lines[line_idx].split()))
            line_idx += 1
            num_eligible = parts[0]
            eligible = []
            idx = 1
            for _ in range(num_eligible):
                m = parts[idx]
                d = parts[idx+1]
                eligible.append((m, d))
                idx += 2
            ops.append(eligible)
        jobs.append(ops)
    
    return num_jobs, num_machines, jobs


def parse_downtime(filepath):
    """Parse downtime CSV. Returns list of dicts with machine, start, end, reason."""
    downtimes = []
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            downtimes.append({
                'machine': int(row['machine']),
                'start': int(row['start']),
                'end': int(row['end']),
                'reason': row.get('reason', '')
            })
    return downtimes


def parse_policy(filepath):
    """Parse policy JSON."""
    with open(filepath) as f:
        return json.load(f)


def parse_baseline(filepath):
    """Parse baseline solution JSON. Returns (status, makespan, schedule_list)."""
    with open(filepath) as f:
        data = json.load(f)
    return data['status'], data['makespan'], data['schedule']


def parse_baseline_metrics(filepath):
    """Parse baseline metrics JSON."""
    with open(filepath) as f:
        return json.load(f)
