# Model-based control for coupled web-handling systems

For a coupled roll-to-roll process, derive a state representation and inputs
from the supplied dynamics, then linearize consistently around the declared
operating point.  Discretize the resulting model with the simulator's actual
sample interval and verify matrix dimensions and local prediction accuracy
before designing feedback.

An MPC or finite-horizon tracking controller balances state error against
control effort while respecting actuator and safety limits.  Time-varying
references must be represented across the prediction horizon rather than
treated as an unannounced disturbance.  A stabilizing feedback law can provide
a terminal or fallback policy when the online optimization is unavailable.

Tune horizons and weights through simulator experiments, not by assuming one
universal set.  Log the state, reference, and applied control at every step;
then compute performance metrics from the delivered trace and validate that
the logged model, controller parameters, and simulation all use the same state
and input ordering.

