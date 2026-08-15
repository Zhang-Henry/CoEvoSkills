"""
FJSP Baseline Repair Solver.

Strategy:
1. Identify frozen operations and those with downtime violations
2. For frozen ops with downtime violations, must reassign (uses change budget)
3. Use right-shift greedy repair with precedence-aware ordering
4. Minimize makespan while respecting all constraints
"""

from constraints import intervals_overlap


def get_downtime_for_machine(machine, downtimes):
    """Get all downtime windows for a specific machine."""
    return [(dt['start'], dt['end']) for dt in downtimes if dt['machine'] == machine]


def find_earliest_start(machine, earliest, duration, downtimes, machine_intervals):
    """Find earliest start time >= earliest on machine avoiding downtime and existing ops.
    
    Args:
        machine: machine id
        earliest: earliest allowed start time
        duration: processing duration
        downtimes: list of downtime dicts
        machine_intervals: list of (start, end) already scheduled on this machine
    
    Returns: earliest feasible start time
    """
    dt_windows = get_downtime_for_machine(machine, downtimes)
    blocked = sorted(list(dt_windows) + list(machine_intervals))
    
    start = earliest
    changed = True
    max_iterations = 1000
    iteration = 0
    while changed and iteration < max_iterations:
        changed = False
        iteration += 1
        end = start + duration
        for bs, be in blocked:
            if intervals_overlap(start, end, bs, be):
                start = be
                changed = True
                break
    return start


def repair_baseline_strategy(jobs, downtimes, policy, baseline_schedule, prefer_short=False):
    """Repair baseline schedule using right-shift greedy approach.
    
    Args:
        prefer_short: if True, prefer shorter durations over same-machine
    
    Returns: list of operation dicts (the repaired schedule)
    """
    freeze_cfg = policy.get('freeze', {})
    freeze_enabled = freeze_cfg.get('enabled', False)
    freeze_until = freeze_cfg.get('freeze_until', 0) if freeze_enabled else 0
    lock_fields = freeze_cfg.get('lock_fields', []) if freeze_enabled else []
    
    budget = policy.get('change_budget', {})
    max_mc = budget.get('max_machine_changes', float('inf'))
    max_l1 = budget.get('max_total_start_shift_L1', float('inf'))
    
    baseline_map = {}
    for op in baseline_schedule:
        baseline_map[(op['job'], op['op'])] = op
    
    # Determine frozen ops
    frozen_ops = set()
    if freeze_enabled:
        for key, op in baseline_map.items():
            if op['start'] < freeze_until:
                frozen_ops.add(key)
    
    # Check which frozen ops have downtime violations
    frozen_with_violations = set()
    for key in frozen_ops:
        op = baseline_map[key]
        m, s, e = op['machine'], op['start'], op['end']
        for dt in downtimes:
            if dt['machine'] == m and intervals_overlap(s, e, dt['start'], dt['end']):
                frozen_with_violations.add(key)
                break
    
    # Build processing order
    pos_map = {}
    for i, op in enumerate(baseline_schedule):
        pos_map[(op['job'], op['op'])] = i
    
    all_keys = list(baseline_map.keys())
    processing_order = sorted(all_keys, key=lambda k: (
        k[1],  # op index
        baseline_map[k]['start'],  # baseline start
        pos_map.get(k, 0)  # original position
    ))
    
    # Track state
    machine_intervals = {}  # machine -> list of (start, end)
    job_end_times = {}  # job -> end time of last placed op
    
    result = []
    machine_changes_used = 0
    total_l1_shift = 0
    
    for key in processing_order:
        j, o = key
        bl_op = baseline_map[key]
        is_frozen = key in frozen_ops
        has_dt_violation = key in frozen_with_violations
        
        # Determine anchor: max(baseline_start, predecessor_end)
        anchor = bl_op['start']
        if o > 0 and j in job_end_times:
            anchor = max(anchor, job_end_times[j])
        
        # Frozen op without downtime violation: keep as-is
        if is_frozen and not has_dt_violation:
            new_op = dict(bl_op)
            # But we need to check if predecessor pushed anchor past frozen start
            # If so, we must shift (breaking freeze) or accept it
            if anchor > bl_op['start']:
                # Predecessor end is after frozen start - we must shift
                # This means freeze is broken by necessity
                pass  # Fall through to general placement
            else:
                machine_intervals.setdefault(new_op['machine'], []).append(
                    (new_op['start'], new_op['end'])
                )
                job_end_times[j] = new_op['end']
                result.append(new_op)
                continue
        
        # For ops that need placement (non-frozen, or frozen with violations)
        eligible = jobs[j][o]
        bl_machine = bl_op['machine']
        
        candidates = []
        for m, d in eligible:
            m_intervals = machine_intervals.get(m, [])
            s = find_earliest_start(m, anchor, d, downtimes, m_intervals)
            e = s + d
            
            is_machine_change = (m != bl_machine)
            mc_after = machine_changes_used + (1 if is_machine_change else 0)
            l1_after = total_l1_shift + abs(s - bl_op['start'])
            
            budget_ok = mc_after <= max_mc and l1_after <= max_l1
            
            if prefer_short:
                sort_key = (0 if budget_ok else 1, d, e, 1 if is_machine_change else 0)
            else:
                sort_key = (0 if budget_ok else 1, e, 1 if is_machine_change else 0, d)
            
            candidates.append((sort_key, s, m, d, is_machine_change))
        
        candidates.sort()
        best = candidates[0]
        _, s, m, d, is_mc = best
        
        new_op = {
            'job': j, 'op': o, 'machine': m,
            'start': s, 'end': s + d, 'dur': d
        }
        
        machine_intervals.setdefault(m, []).append((s, s + d))
        job_end_times[j] = s + d
        if is_mc:
            machine_changes_used += 1
        total_l1_shift += abs(s - bl_op['start'])
        result.append(new_op)
    
    return result


def try_alternative_schedules(jobs, downtimes, policy, baseline_schedule):
    """Try multiple strategies and return the best feasible schedule."""
    from constraints import validate_schedule
    
    best_schedule = None
    best_makespan = float('inf')
    
    strategies = [
        ('end_time', False),
        ('short_dur', True),
    ]
    
    for name, prefer_short in strategies:
        sched = repair_baseline_strategy(jobs, downtimes, policy, baseline_schedule, prefer_short)
        issues = validate_schedule(sched, jobs, downtimes, policy, baseline_schedule)
        ms = max(op['end'] for op in sched)
        print(f"Strategy {name}: makespan={ms}, issues={list(issues.keys()) if issues else 'none'}")
        if not issues and ms < best_makespan:
            best_schedule = sched
            best_makespan = ms
    
    if best_schedule is not None:
        return best_schedule
    
    # If no strategy produced a fully valid schedule, return the one with fewest issues
    results = []
    for name, prefer_short in strategies:
        sched = repair_baseline_strategy(jobs, downtimes, policy, baseline_schedule, prefer_short)
        issues = validate_schedule(sched, jobs, downtimes, policy, baseline_schedule)
        results.append((len(issues), sched, issues))
    results.sort()
    print(f"Best fallback has {results[0][0]} issue types: {list(results[0][2].keys())}")
    return results[0][1]
