# General Reflow-Process Measurement Principles

This document summarizes public engineering concepts used when interpreting reflow-oven measurements. It does not define the acceptance policy for a particular factory or dataset. Zone boundaries, allowable limits, alloy references, sensor-selection rules, missing-data treatment, and run-ranking rules must be read from the supplied handbook and records at runtime.

## Thermal-profile concepts

A reflow profile is a temperature-versus-time trace measured on an assembly as it moves through an oven. A typical profile includes preheat, soak, reflow, and cooling phases. Their exact boundaries are process-specific rather than universal.

Thermocouples at different board locations can produce different traces because components and copper areas have different thermal masses. Consequently, a compliance calculation must preserve the sensor identity and must use whatever aggregation or representative-sensor rule the governing handbook specifies.

Temperature is commonly reported in degrees Celsius, time in seconds, and a temperature ramp in degrees Celsius per second. Timestamps and temperatures should be converted to consistent units before calculations.

## Temperature ramp

For two ordered samples \((t_1,T_1)\) and \((t_2,T_2)\), with \(t_2>t_1\), the segment ramp is

\[
r = \frac{T_2-T_1}{t_2-t_1}.
\]

Before aggregating segment ramps, determine from the handbook:

- how preheat is delimited;
- whether boundary-crossing segments are included or interpolated;
- whether heating ramps, absolute ramps, or another statistic is required;
- how multiple thermocouples are combined; and
- the allowable limit and its units.

Do not substitute a remembered temperature band or limit for the process-specific definition.

## Time above a reference temperature

Time Above Liquidus (TAL) is the duration for which a temperature trace is above the applicable solder reference temperature. The relevant reference may vary with solder material or process record and must be obtained from the supplied evidence.

With discrete samples, a threshold crossing between \((t_1,T_1)\) and \((t_2,T_2)\) can be estimated by linear interpolation:

\[
t_{cross}=t_1+(t_2-t_1)\frac{T_{ref}-T_1}{T_2-T_1}.
\]

The durations of the above-threshold portions of all segments can then be summed. Special cases such as equal endpoint temperatures, duplicate timestamps, gaps, and missing sensors should be handled explicitly. The handbook remains authoritative for the TAL window, comparison inclusivity, sensor-selection rule, and rounding.

## Peak temperature

The peak of one trace is its maximum valid temperature sample (or another handbook-defined estimate). A process requirement may compare the peak with a material-dependent reference plus a margin, but neither that margin nor the rule for combining sensors is universal. Read those rules from the handbook. Absence of usable measurements is an evidence-quality condition whose final treatment must also follow the task specification or handbook.

## Conveyor speed and dwell

Conveyor speed relates traveled distance and elapsed time:

\[
v=\frac{d}{t}.
\]

For regularly spaced boards, pitch is board length in the travel direction plus inter-board spacing. If a loading factor is defined as \(L/(L+S)\), then equivalent throughput expressions can be derived algebraically. Heated length and required dwell time can likewise imply a process speed. Length and time units must be normalized before comparing values.

The handbook may define feasibility as a lower bound, upper bound, interval, or conjunction of several constraints. It may also specify which board dimension, spacing convention, or loading factor applies. These are runtime rules, not general constants.

## Inspection and maintenance evidence

Automated optical inspection, X-ray inspection, and visual inspection detect different defect classes. Yield, defect counts, severity, throughput, downtime, and compliance can all be relevant to maintenance decisions, but there is no universal formula for selecting a preferred production run. Use only ranking priorities and tie-breakers stated in the instruction or handbook; otherwise report the evidence without inventing weights.

## Evidence-driven workflow

1. Inspect the supplied handbook and record its definitions, formulas, limits, inclusivity rules, and units with page references.
2. Discover the runtime data schema instead of assuming column names or fixed layouts.
3. Establish joins between runs, sensors, process settings, and inspection records from observed identifiers.
4. Calculate per-trace quantities first, then apply the handbook's aggregation rules.
5. Check unit consistency, timestamp ordering, threshold crossings, missing records, and rounding.
6. Recompute a small sample independently and ensure every reported decision can be traced to handbook text and input data.
