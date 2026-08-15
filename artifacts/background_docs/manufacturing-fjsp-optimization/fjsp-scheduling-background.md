# Flexible Job-Shop Scheduling and Baseline Repair

This document provides background on the Flexible Job-Shop Scheduling Problem (FJSP), machine downtime constraints, and policy-governed baseline repair strategies used in manufacturing production planning.

## The Flexible Job-Shop Scheduling Problem

The classical Job-Shop Scheduling Problem (JSP) assigns operations to machines in a fixed sequence. The **Flexible** variant (FJSP) relaxes the machine assignment: each operation may be processed on one of several eligible machines, each with a potentially different processing duration. The scheduler must decide both *which machine* processes each operation and *when* it starts.

An FJSP instance is defined by:

- **J jobs**, each consisting of an ordered sequence of operations.
- **M machines** numbered 0 through M-1.
- For each operation, a set of (machine, duration) pairs specifying which machines can perform it and how long each would take.

The standard instance file format encodes this compactly. The first line gives J and M. Each subsequent job block starts with the number of operations in that job. For each operation, the first number gives how many machine options exist, followed by pairs of (machine_id, processing_time). For an unrelated synthetic example, `3 0 8 2 5 4 7` means three eligible machines: machine 0 takes 8 time units, machine 2 takes 5, and machine 4 takes 7.

### Fundamental Constraints

A valid FJSP schedule must satisfy three hard constraints simultaneously:

1. **Machine eligibility**: Each operation must be assigned to one of its eligible machines, and the duration must match the processing time specified for that machine in the instance data. Using an ineligible machine or the wrong duration for a given machine renders the schedule invalid.

2. **Precedence (intra-job ordering)**: Operations within the same job must execute in strict sequence. If job j has operations 0, 1, 2, then operation 1 cannot start until operation 0 finishes, and operation 2 cannot start until operation 1 finishes. Formally, for consecutive operations o and o+1 of the same job: end(j, o) <= start(j, o+1).

3. **No machine overlap (resource exclusivity)**: A machine can process only one operation at a time. If two operations are assigned to the same machine, their time intervals must not overlap. Intervals are treated as half-open: operation scheduled at [s, e) occupies the machine from time s up to but not including time e, so one operation ending at time t and another starting at t is permissible (no overlap).

### Makespan

The **makespan** is the completion time of the last operation to finish across all jobs. It equals the maximum end value across every operation in the schedule. This is the primary optimization objective: minimize makespan. When reporting makespan, it must exactly equal the computed maximum end time across all scheduled operations.

### Schedule Representation

Each row of a schedule specifies six fields for one operation:

- **job**: the job index (0-based)
- **op**: the operation index within that job (0-based)
- **machine**: the assigned machine index
- **start**: when processing begins
- **end**: when processing finishes
- **dur**: processing duration

The invariant end = start + dur must hold for every operation. A complete schedule contains exactly one row per operation across all jobs, with no duplicates and no missing entries.

## Machine Downtime Windows

In real manufacturing environments, machines are periodically unavailable due to planned maintenance, preventive maintenance (PM), calibration, or other operational reasons. A **downtime window** specifies a half-open interval [start, end) during which a given machine cannot process any operation.

A schedule is **downtime-feasible** if no operation's processing interval overlaps with any downtime window on its assigned machine. Overlap between half-open intervals [a, b) and [c, d) exists when a < d and c < b. An operation ending exactly when downtime begins (or starting exactly when downtime ends) does not constitute a violation.

When an existing baseline schedule has downtime violations, the primary repair objective is to eliminate all of them. A repaired schedule must have zero downtime violations.

## Baseline Repair vs. From-Scratch Scheduling

In many industrial settings, the task is not to build a schedule from nothing but to **repair** an existing baseline schedule that has become infeasible (typically due to newly introduced or updated downtime windows). The repair problem is fundamentally different from green-field scheduling because it must preserve the baseline's structure as much as possible while eliminating violations.

### Right-Shift-Only Repair

A common constraint in baseline repair is the **right-shift-only** rule: every operation in the repaired schedule must start at or after its baseline start time. No operation may be moved earlier. This reflects the practical reality that operations already committed or partially prepared cannot be advanced, only delayed.

Formally, for every (job, op) pair: new_start(j, o) >= baseline_start(j, o).

This constraint has a cascading effect. When an operation is shifted right to avoid a downtime window, its successors in the same job may also need to shift right to maintain precedence. Those shifts may in turn cause machine conflicts with other operations, requiring further shifts. A correct repair must propagate these ripple effects through the entire schedule.

### Local Minimality

Beyond simply satisfying feasibility, a high-quality right-shift repair is **locally minimal**: each operation starts as early as possible given the constraints it faces. An operation should not be shifted further right than necessary.

More precisely, for each operation processed in a well-defined order, the operation's start time should be the earliest feasible time at or after its **anchor point**. The anchor point is the later of:

- The operation's baseline start time (right-shift constraint)
- The end time of the preceding operation in the same job (precedence constraint)

If the operation's actual start time equals the anchor, no further justification is needed. If the start time exceeds the anchor, it must be because starting one time unit earlier would cause a conflict with either another operation already placed on the same machine or a downtime window on that machine.

### Processing Order for Repair

The order in which operations are considered during repair matters. A **precedence-aware** ordering processes operations by:

1. **Operation index ascending** (primary): all op-0 operations across jobs before any op-1, all op-1 before any op-2, etc. This guarantees that when placing operation (j, o), operation (j, o-1) has already been placed and its end time is known.
2. **Baseline start time ascending** (secondary): among operations with the same operation index, those with earlier baseline starts are placed first.
3. **Original list position** (tertiary): stable tie-breaker for operations with identical operation index and baseline start time.

This ordering ensures that precedence constraints are naturally satisfied during greedy left-to-right placement and that machine interval bookkeeping is consistent.

## Policy Constraints

Manufacturing schedules operate under organizational policies that limit how much a repaired schedule may deviate from the baseline. These policies serve business continuity, contractual obligations, and operational stability.

### Change Budgets

A **change budget** caps the total amount of modification allowed:

- **Maximum machine changes**: The total number of operations reassigned to a different machine than in the baseline. If an operation stays on the same machine (even if shifted in time), it does not count as a machine change.
- **Maximum total start shift (L1 norm)**: The sum of absolute differences in start times across all operations. This measures aggregate schedule disruption. Each operation contributes |new_start - baseline_start| to this total.

Both limits must be respected simultaneously. A repair that reassigns too many operations to different machines or shifts start times by too large a cumulative amount is considered policy-infeasible even if it is otherwise a valid schedule.

### Freeze Windows

A **freeze policy** locks certain fields of operations that begin before a specified time horizon. If an operation's baseline start time falls before the freeze boundary, the specified fields (such as machine assignment, start time, and end time) must remain identical to the baseline.

The freeze protects near-term committed work. Operations starting after the freeze boundary are free to be modified within the other policy limits. Note that the policy may use different key names for the freeze threshold and locked fields, so implementations must be flexible in how they parse these fields.

### Interaction Between Constraints

All constraints --- feasibility (machine eligibility, precedence, no overlap), downtime avoidance, right-shift-only, local minimality, change budgets, and freeze policies --- must be satisfied simultaneously. A common failure mode is optimizing for one constraint while inadvertently violating another. For instance, reassigning an operation to a different machine to avoid downtime may satisfy downtime feasibility but violate the machine change budget or freeze policy.

## Output Consistency Requirements

When a task requires both a JSON solution and a CSV schedule, these outputs must represent exactly the same data. Every operation present in one format must appear in the other, with identical values for all core fields (job, op, machine, start, end, dur). The comparison is order-independent --- rows need not appear in the same sequence --- but the sets of operation tuples must match exactly.

The JSON output must also include the reported makespan, which must be computed correctly as the maximum end time, and a non-empty status string.

## Important Technical Details

**Cascading effects of right-shift propagation.** Shifting one operation to avoid a downtime window initiates a chain of potential adjustments. That shift may push successors in the same job past their original start times, and those successor shifts may create new machine overlaps with other operations, requiring further shifts. A complete repair algorithm propagates these ripple effects through the entire schedule until all constraints are simultaneously satisfied.

**Half-open interval semantics for overlap detection.** Intervals in FJSP scheduling are half-open: [start, end). Two intervals [a, b) and [c, d) overlap if and only if a < d and c < b. An operation ending at time t and another beginning at time t do not overlap -- this is a permissible back-to-back placement. Using closed intervals or strict inequalities instead of the standard half-open convention produces incorrect conflict detection.

**Zero-based indexing convention.** Instance files, job indices, operation indices, and machine indices in FJSP are all 0-based. Consistent use of 0-based indexing throughout the solution ensures that machine eligibility checks, job references, and operation keys align correctly with the instance data.

**Policy budget tracking during repair.** Each machine reassignment consumes part of the machine change budget, and each start time shift accumulates against the L1 shift budget. A repair strategy tracks these running totals throughout the process, ensuring that neither limit is breached even as multiple individual adjustments are made to resolve downtime violations.

**Freeze constraint enforcement on early operations.** Operations whose baseline start falls within the frozen time horizon must remain completely unchanged in their frozen fields (typically machine assignment, start time, and end time). The freeze protects near-term committed work and takes precedence over repair optimization for affected operations.

**Complete (job, op) key set preservation.** The repaired schedule must contain exactly the same set of (job, op) pairs as the baseline, with no additions, omissions, or duplicates. The repair modifies timing and potentially machine assignment but does not alter the structural composition of the schedule.

**Makespan computation from actual schedule data.** The makespan equals the maximum end time across all operations in the schedule. It is derived directly from the scheduled operation end times rather than estimated or carried over from the baseline, ensuring that the reported value accurately reflects the repaired schedule's completion time.
