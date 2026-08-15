def intervals_overlap(s1, e1, s2, e2):
    """Check if half-open intervals [s1,e1) and [s2,e2) overlap."""
    return s1 < e2 and s2 < e1


def check_downtime_violations(schedule, downtimes):
    """Return list of operations that violate downtime windows."""
    violations = []
    for op in schedule:
        m = op['machine']
        s = op['start']
        e = op['end']
        for dt in downtimes:
            if dt['machine'] == m and intervals_overlap(s, e, dt['start'], dt['end']):
                violations.append((op['job'], op['op'], m, s, e, dt))
    return violations


def check_precedence(schedule):
    """Check intra-job precedence. Returns list of violations."""
    by_job = {}
    for op in schedule:
        by_job.setdefault(op['job'], {})[op['op']] = op
    violations = []
    for j, ops in by_job.items():
        max_op = max(ops.keys())
        for o in range(max_op):
            if o in ops and (o+1) in ops:
                if ops[o]['end'] > ops[o+1]['start']:
                    violations.append((j, o, o+1))
    return violations


def check_machine_overlap(schedule):
    """Check no two ops on same machine overlap. Returns violations."""
    by_machine = {}
    for op in schedule:
        by_machine.setdefault(op['machine'], []).append(op)
    violations = []
    for m, ops in by_machine.items():
        ops_sorted = sorted(ops, key=lambda x: x['start'])
        for i in range(len(ops_sorted)-1):
            if intervals_overlap(ops_sorted[i]['start'], ops_sorted[i]['end'],
                                ops_sorted[i+1]['start'], ops_sorted[i+1]['end']):
                violations.append((m, ops_sorted[i], ops_sorted[i+1]))
    return violations


def check_eligibility(schedule, jobs):
    """Check each op is assigned to an eligible machine with correct duration."""
    violations = []
    for op in schedule:
        j, o, m, dur = op['job'], op['op'], op['machine'], op['dur']
        eligible = jobs[j][o]
        valid = any(em == m and ed == dur for em, ed in eligible)
        if not valid:
            violations.append((j, o, m, dur, eligible))
    return violations


def check_end_equals_start_plus_dur(schedule):
    """Verify end = start + dur for all ops."""
    violations = []
    for op in schedule:
        if op['end'] != op['start'] + op['dur']:
            violations.append(op)
    return violations


def compute_policy_metrics(new_schedule, baseline_schedule):
    """Compute policy metrics: machine changes and L1 start shift."""
    baseline_map = {}
    for op in baseline_schedule:
        baseline_map[(op['job'], op['op'])] = op
    
    machine_changes = 0
    total_start_shift = 0
    for op in new_schedule:
        key = (op['job'], op['op'])
        bl = baseline_map[key]
        if op['machine'] != bl['machine']:
            machine_changes += 1
        total_start_shift += abs(op['start'] - bl['start'])
    
    return machine_changes, total_start_shift


def check_freeze(new_schedule, baseline_schedule, policy):
    """Check freeze constraints. Returns list of violations."""
    freeze_cfg = policy.get('freeze', {})
    if not freeze_cfg.get('enabled', False):
        return []
    
    freeze_until = freeze_cfg.get('freeze_until', 0)
    lock_fields = freeze_cfg.get('lock_fields', [])
    
    baseline_map = {}
    for op in baseline_schedule:
        baseline_map[(op['job'], op['op'])] = op
    
    violations = []
    for op in new_schedule:
        key = (op['job'], op['op'])
        bl = baseline_map[key]
        if bl['start'] < freeze_until:
            for field in lock_fields:
                if op.get(field) != bl.get(field):
                    violations.append((key, field, bl.get(field), op.get(field)))
    return violations


def check_right_shift(new_schedule, baseline_schedule):
    """Check right-shift-only: new_start >= baseline_start."""
    baseline_map = {}
    for op in baseline_schedule:
        baseline_map[(op['job'], op['op'])] = op
    violations = []
    for op in new_schedule:
        key = (op['job'], op['op'])
        bl = baseline_map[key]
        if op['start'] < bl['start']:
            violations.append((key, bl['start'], op['start']))
    return violations


def validate_schedule(schedule, jobs, downtimes, policy, baseline_schedule):
    """Run all validations. Returns dict of issues."""
    issues = {}
    
    v = check_end_equals_start_plus_dur(schedule)
    if v: issues['end_not_start_plus_dur'] = v
    
    v = check_eligibility(schedule, jobs)
    if v: issues['eligibility'] = v
    
    v = check_precedence(schedule)
    if v: issues['precedence'] = v
    
    v = check_machine_overlap(schedule)
    if v: issues['machine_overlap'] = v
    
    v = check_downtime_violations(schedule, downtimes)
    if v: issues['downtime'] = v
    
    v = check_right_shift(schedule, baseline_schedule)
    if v: issues['right_shift'] = v
    
    v = check_freeze(schedule, baseline_schedule, policy)
    if v: issues['freeze'] = v
    
    mc, l1 = compute_policy_metrics(schedule, baseline_schedule)
    budget = policy.get('change_budget', {})
    max_mc = budget.get('max_machine_changes', float('inf'))
    max_l1 = budget.get('max_total_start_shift_L1', float('inf'))
    if mc > max_mc:
        issues['machine_change_budget'] = (mc, max_mc)
    if l1 > max_l1:
        issues['l1_shift_budget'] = (l1, max_l1)
    
    # Check completeness
    expected = set()
    for j, job_ops in enumerate(jobs):
        for o in range(len(job_ops)):
            expected.add((j, o))
    actual = set((op['job'], op['op']) for op in schedule)
    if expected != actual:
        issues['completeness'] = {'missing': expected - actual, 'extra': actual - expected}
    
    # Makespan ratio
    guards = policy.get('guards', {})
    max_ratio = guards.get('max_makespan_ratio', float('inf'))
    baseline_makespan = max(op['end'] for op in baseline_schedule)
    new_makespan = max(op['end'] for op in schedule)
    if new_makespan > baseline_makespan * max_ratio:
        issues['makespan_ratio'] = (new_makespan, baseline_makespan * max_ratio)
    
    return issues
