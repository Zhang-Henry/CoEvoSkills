# Thermal system identification and feedback control

A room-heating process can often be approximated locally by a stable
first-order system with heat loss to the environment.  A useful calibration
experiment records time, temperature, and applied power at a sufficiently fine
cadence while deliberately exciting the plant.  Fit parameters from the
recorded response and assess the fit against the observations instead of
assuming nominal dynamics.

For closed-loop control, proportional action reacts to present error,
integral action removes persistent offset, and derivative action can damp rapid
changes but is sensitive to noise.  Clamp actuator commands to their physical
range and prevent integral windup while saturated.  Controller tuning should
be derived from the identified model and then checked in the actual simulator.

Compute performance metrics from the delivered control trace using explicit,
documented definitions.  Reopen every generated artifact and verify that its
records are finite, time ordered, internally consistent, and long enough to
support the reported conclusions.

