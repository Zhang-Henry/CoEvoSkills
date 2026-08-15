# Adaptive Cruise Control Systems

This document provides background on Adaptive Cruise Control (ACC) system design, covering PID-based control theory, multi-mode ACC architectures, safe following distance models, and the physics of longitudinal vehicle dynamics. It is intended to equip someone unfamiliar with the domain with the reasoning needed to design, tune, and validate an ACC simulation from scratch.

## PID Control Fundamentals

A PID (Proportional-Integral-Derivative) controller is the workhorse of classical control engineering. It computes a control output based on three terms derived from the error signal (the difference between a desired setpoint and the measured process variable):

- **Proportional (P)**: Output is proportional to the current error. A larger proportional gain drives faster correction but can cause oscillation if set too high.
- **Integral (I)**: Output is proportional to the accumulated error over time. This eliminates steady-state error (the persistent gap between setpoint and actual value that pure P control cannot close). Excessive integral gain causes integral windup, where accumulated error produces overshoot and sluggish recovery.
- **Derivative (D)**: Output is proportional to the rate of change of error. This provides damping that anticipates future error, reducing overshoot and oscillation. Noise sensitivity increases with derivative gain.

The standard discrete-time PID update proceeds as follows. At each timestep, the integral accumulator is incremented by the product of the current error and the timestep duration dt. The derivative term is computed as the difference between the current error and the previous error, divided by dt. The controller output is then the sum of three terms: the proportional gain times the error, the integral gain times the integral, and the derivative gain times the derivative. Finally, the previous error is updated to the current error for use in the next step.

### Tuning Considerations

ACC systems typically use two separate PID controllers: one for speed control (maintaining a target cruise speed) and one for distance control (maintaining a safe following gap). Each controller has its own gains because the dynamics of speed tracking and gap regulation are fundamentally different.

**Speed controller**: The plant being controlled is vehicle longitudinal dynamics, where the input is acceleration command and the output is vehicle speed. The error is the difference between set speed and ego speed. Because speed is the integral of acceleration, a proportional-only controller with moderate gain can produce reasonably fast response, but integral action is needed to eliminate steady-state error caused by drag, road grade, and model mismatch.

**Distance controller**: The plant is relative dynamics between the ego vehicle and the lead vehicle, where the input is again the ego acceleration command but the output is the inter-vehicle gap. The error is the difference between desired distance and actual distance. This loop is more complex because the lead vehicle's speed is an uncontrolled disturbance. The controller must be tuned conservatively enough to avoid aggressive acceleration/deceleration cycles when the lead vehicle speed fluctuates.

**General tuning heuristics**:

| Gain increased | Rise time | Overshoot | Settling time | Steady-state error |
|---|---|---|---|---|
| Proportional | Decreases | Increases | Small change | Decreases |
| Integral | Decreases | Increases | Increases | Eliminates |
| Derivative | Small change | Decreases | Decreases | No effect |

A practical tuning approach: start with integral and derivative gains at zero, increase the proportional gain until acceptable rise time is achieved, then add integral gain to eliminate steady-state offset, and finally add derivative gain to reduce overshoot and oscillation. Gains that are too large in any term produce instability or unacceptable oscillation.

### Integral Windup and Clamping

When the controller output is saturated (e.g., acceleration is clamped to physical limits), the integral term can continue accumulating error, leading to windup. When saturation finally lifts, the bloated integral produces massive overshoot. Mitigation strategies include clamping the integral accumulator to a bounded range, or using back-calculation anti-windup where the integral is adjusted based on the difference between the commanded and saturated output.

## ACC Operating Modes

An ACC system operates in distinct modes depending on the traffic situation. Mode selection logic is the backbone of the system's behavior.

### Cruise Mode

When no lead vehicle is detected by the forward-facing sensors, the ACC operates as a conventional cruise control. The speed PID controller drives the ego vehicle toward the set speed. The control loop is straightforward: the error is computed as the difference between set speed and ego speed, and the acceleration command is produced by feeding this error and the timestep into the speed PID controller.

In cruise mode, distance-related quantities (following gap, distance error, time-to-collision) are undefined because there is no lead vehicle to track.

### Follow Mode

When a lead vehicle is detected and the situation is not an emergency, the ACC switches to gap-regulation mode. The system computes a desired safe following distance and uses the distance PID controller to maintain it.

The desired distance is typically computed using a time-headway model (described in the next section). The desired distance equals the product of the time headway and the ego speed, plus the minimum standstill distance. The distance error is then the difference between desired distance and actual distance.

A positive error means the ego vehicle is too close and should decelerate; a negative error means there is excess gap and the vehicle may accelerate (up to the set speed). The distance controller output is an acceleration command, but it should be further bounded so that the ego vehicle never accelerates beyond what the speed controller would command in cruise mode -- the ACC should not exceed the set speed just because the gap is large.

### Emergency Mode

When the Time-to-Collision (TTC) drops below a critical threshold, the system enters emergency mode and applies maximum deceleration to avoid a collision. This mode overrides both cruise and follow logic. The acceleration command in emergency mode should always be strongly negative (hard braking), regardless of what the PID controllers compute.

Emergency mode activates based on TTC, not distance alone. A large gap at high closing speed can be more dangerous than a small gap with matched speeds.

### Mode Transition Logic

The mode selection hierarchy follows safety priority:

1. If TTC is defined and below the emergency threshold, enter **emergency** mode.
2. If a lead vehicle is detected (lead speed and distance are available), enter **follow** mode.
3. Otherwise, enter **cruise** mode.

TTC is only defined when the ego vehicle is approaching the lead vehicle (ego speed exceeds lead speed). When the lead vehicle is faster or moving away, TTC is undefined (or effectively infinite) and should not be reported.

When transitioning between modes, PID controller state management matters. Switching from cruise to follow (or vice versa) without resetting the inactive controller's integral accumulator can cause transient spikes when that controller next becomes active.

## Safe Following Distance Models

The most widely used model for computing a safe following distance in ACC systems is the **constant time-headway** policy. The safe distance is computed as d_safe = time_headway * v_ego + d_min, where:

- time_headway is the desired time gap (in seconds) between the ego vehicle and the lead vehicle. At constant speed, this represents how many seconds of travel separate the two vehicles. Typical highway values range from 1.0 to 2.0 seconds.
- v_ego is the ego vehicle's current speed (m/s).
- d_min is a minimum standstill distance (meters) that provides a safety buffer even when the ego vehicle is stationary or moving very slowly.

This model is speed-dependent: at higher speeds, the required gap grows linearly. This is physically intuitive -- at higher speeds, more distance is needed to react and brake safely. At very low speeds, d_min dominates to prevent bumper-to-bumper proximity.

**Distance error** in follow mode is d_safe - d_actual. A positive value means the ego is closer than desired (needs to slow down); a negative value means the ego has excess gap (may speed up).

## Time-to-Collision (TTC)

TTC estimates how many seconds remain before a rear-end collision, assuming both vehicles maintain their current speeds. When the ego vehicle is faster than the lead vehicle (v_ego > v_lead), TTC is computed as distance / (v_ego - v_lead). When the ego vehicle is slower than or equal in speed to the lead vehicle (v_ego <= v_lead), TTC is undefined because there is no closing trajectory.

Key properties:

- TTC is only meaningful when the ego vehicle is **closing** on the lead vehicle (positive relative speed). When the lead is pulling away or speeds are matched, there is no collision trajectory and TTC should not be computed.
- TTC decreases as the gap shrinks or the closing speed increases. A low TTC signals imminent danger regardless of the absolute distance.
- TTC is a **conservative** metric -- it assumes no speed changes. In practice, both vehicles may accelerate or brake, so actual collision risk may differ. But as a trigger for emergency braking, the constant-speed assumption provides an appropriate safety margin.

The ACC uses TTC to trigger emergency mode: when TTC drops below the configured threshold, the system overrides normal control and applies maximum braking. This is a hard safety boundary that should never be softened by PID logic.

## Longitudinal Vehicle Dynamics

The simulation models a simplified longitudinal (forward/backward) vehicle dynamic. At each timestep, the new speed is computed as the current speed plus the product of the current acceleration and the timestep: v(t + dt) = v(t) + a(t) * dt. The new position is the current position plus the product of the current speed and the timestep: x(t + dt) = x(t) + v(t) * dt. Where v is speed, a is acceleration, and x is position. This is a first-order Euler integration, appropriate for the time step sizes used in ACC simulation.

### Acceleration Limits

Real vehicles have asymmetric acceleration capability:

- **Maximum acceleration** is limited by engine power and traction. Typical passenger vehicles achieve modest positive acceleration (a few m/s^2).
- **Maximum deceleration** is limited by braking system capability and tire grip. Emergency braking can achieve much higher magnitudes than maximum acceleration.

The controller's raw output must be clamped to these physical limits before being applied to the vehicle model. Any acceleration command outside the feasible range is saturated at the limit.

### Non-Negative Speed Constraint

Vehicle speed cannot go negative in a forward-driving simulation. If deceleration would drive speed below zero within a time step, speed should be clamped to zero. This is especially relevant during emergency braking at low speeds.

### Distance Update with Lead Vehicle

When a lead vehicle is present, the inter-vehicle distance changes based on relative speed. The updated distance equals the current distance plus the product of the relative speed (lead minus ego) and the timestep: distance(t + dt) = distance(t) + (v_lead - v_ego) * dt.

If the ego vehicle is faster than the lead, the distance decreases. If the lead is faster, the distance increases. The simulation should use the sensor-provided lead vehicle speed for this calculation, as the ego vehicle's ACC has no direct control over the lead vehicle's behavior.

## Sensor Data and Simulation Architecture

An ACC simulation is driven by sensor data representing the external traffic environment. The ego vehicle's speed is a controlled variable (output of the simulation), while the lead vehicle's speed and initial distance conditions come from sensor observations.

### Data-Driven Lead Vehicle Behavior

The sensor data provides time-stamped observations of the lead vehicle's speed and distance. When the lead vehicle is absent (no detection), these fields are empty. The simulation must:

- Use lead vehicle data from the sensor when present to determine mode and compute TTC/distance error.
- Treat empty lead vehicle fields as "no lead detected" and operate in cruise mode.
- **Not** use the sensor's ego speed as the simulated ego speed. The ego speed in the simulation output should be the result of integrating the controller's acceleration commands from the initial condition, not a copy of the sensor recording. The sensor ego speed represents the original recording; the simulation re-derives ego speed under the ACC controller's commands.

### Output Alignment

The simulation should produce output at the same timestamps as the sensor input. Each row of output corresponds to one simulation step, with the controller processing the current state and producing an acceleration command that is then integrated to compute the next state.

For columns that are only meaningful in certain modes:

- Distance error, distance, and TTC should be empty/absent in cruise mode (no lead vehicle).
- TTC should be empty when the ego vehicle is not approaching the lead (lead is faster or same speed).

## Practical Considerations

The following principles are fundamental to correct ACC system design:

- **Ego speed is derived from the control loop, not from sensor recordings.** The simulation integrates acceleration commands from an initial condition to produce the ego speed trajectory. The sensor ego speed represents the original recording conditions; the simulation re-derives ego speed under the ACC controller's commands. Using sensor ego speed directly bypasses the entire control loop.

- **Acceleration commands are bounded by physical vehicle limits.** The PID controller's raw output must be clamped to the feasible range of the vehicle's acceleration capability before being applied to the dynamics model. Unbounded commands can produce physically impossible accelerations, breaking the realism of the simulation.

- **Emergency mode is triggered by time-to-collision, not distance alone.** TTC is a rate-based metric that accounts for closing speed, making it a more appropriate trigger for emergency braking than a simple distance threshold. A vehicle at 5 m distance with matched speeds is in a stable situation, while a vehicle at 50 m distance with high closing speed may face imminent collision.

- **TTC is defined only when the ego vehicle is closing on the lead.** When the ego speed is less than or equal to the lead speed, there is no collision trajectory. TTC is undefined in this case, and computing it would produce negative or infinite values that do not represent a meaningful physical quantity.

- **PID controller state is reset on mode transitions.** When switching between speed and distance controllers, the inactive controller's integral accumulator may contain stale values. Resetting the integral term (or the entire controller state) upon mode entry prevents transient spikes that would otherwise occur when the controller becomes active with an outdated accumulated error.

- **The standstill distance provides a minimum safety buffer.** The safe following distance formula includes a minimum standstill distance component that ensures a nonzero gap even at very low ego speeds. Without this term, the desired distance approaches zero as speed approaches zero, which is physically unsafe in stop-and-go traffic.

- **PID gains are configuration parameters, not fixed constants.** For a tunable system, gains are read from a configuration source at runtime. This separation of configuration from logic enables systematic tuning experiments and makes the system adaptable to different vehicle platforms and driving conditions.

- **Only one control mode is active at a time.** In follow mode, the distance controller governs the acceleration command. The speed controller is not simultaneously active. If both controllers produced commands concurrently, they could conflict — the speed controller trying to reach set speed while the distance controller tries to maintain a gap. The mode selection logic ensures clear priority and prevents conflicting control signals.

- **TTC and distance data are reported only when a lead vehicle is present.** When no lead vehicle is detected, these fields are semantically undefined. The standard practice is to leave them empty rather than filling them with zeros or placeholder values, which would misrepresent the traffic state.
