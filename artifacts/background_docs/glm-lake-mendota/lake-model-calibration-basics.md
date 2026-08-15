# Calibrating a one-dimensional lake model

A one-dimensional lake model resolves vertical heat transport, surface energy
exchange, mixing, inflows, outflows, and optional ice or sediment processes.
Before calibration, verify that forcing coverage, units, time zone, depth
conventions, morphometry, and initial profiles are mutually consistent.

Compare simulated and observed temperatures only after aligning timestamps and
depths.  Calibrate a small set of physically meaningful parameters within
plausible bounds, using a coarse-to-fine or otherwise reproducible search.
Change one coherent parameter group at a time and retain both the objective
value and the model-run status, since a failed run is not a valid calibration
candidate.

The final configuration must itself reproduce the selected simulation.  Run
the model from a clean output directory, confirm the requested time span and
variables in the generated dataset, recompute the reported error from that
file, and check for missing values, truncated periods, or stale outputs.

