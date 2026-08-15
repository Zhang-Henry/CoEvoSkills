# AC Optimal Power Flow (ACOPF)

This document provides background on AC Optimal Power Flow for MATPOWER-style electric-grid models. It covers the physical model, mathematical formulation, data conventions, and important implementation details.

## Power System Fundamentals

A power system is modeled as a graph of **buses** (nodes) connected by **branches** (edges). Each bus may have loads (power consumers), generators (power producers), and/or shunt elements. Each branch represents a transmission line or transformer and is characterized by its electrical parameters (impedance, charging susceptance, tap ratio, phase shift).

All quantities are expressed in a **per-unit (pu) system** normalized to a system-wide base power (baseMVA). Physical MW and MVAr values are converted to pu by dividing by baseMVA, and pu values are converted back by multiplying.

**Complex power** is denoted S = P + jQ, where P is active (real) power in MW and Q is reactive power in MVAr. **Complex voltage** is V = Vm * exp(j * Va), where Vm is the voltage magnitude in pu and Va is the voltage angle in radians. The relationship between power, voltage, and current is S = V * I*, where I* is the complex conjugate of current.

### Bus Types

Power system buses are classified into three types, following the MATPOWER convention:

| BUS_TYPE | Name | Role |
|----------|------|------|
| 1 | PQ (Load) | Active and reactive power are specified (demand). No voltage control. |
| 2 | PV (Generator) | Active power output and voltage setpoint are specified. Reactive power is a free variable within limits. |
| 3 | Slack (Reference) | Provides the angular reference for the system. Its voltage angle is fixed at 0 degrees. It absorbs any system-wide power imbalance. |

Every network must have exactly one reference bus (BUS_TYPE = 3). Its voltage angle is constrained to zero, which provides a unique angular reference frame for all other bus angles.

### Per-Unit System and baseMVA

The per-unit system simplifies calculations by normalizing all power quantities to a common base. In MATPOWER-format data:

- baseMVA is the system base power (typically 100 MVA)
- Bus loads (Pd, Qd) and shunt admittances (Gs, Bs) are stored in MW, MVAr, and MW/MVAr at 1.0 pu voltage respectively, and must be divided by baseMVA before use in per-unit equations
- Generator bounds (Pmin, Pmax, Qmin, Qmax) and outputs (Pg, Qg) are stored in MW/MVAr and must be divided by baseMVA for per-unit calculations
- Branch impedances (r, x) and charging susceptance (b) are already in per-unit
- Branch flow limits (rateA) are in MVA and must be divided by baseMVA for per-unit comparisons

The cost function, however, operates in physical units: Pg in MW, cost in $/hr.

## The Pi-Model for Branches

Every transmission line or transformer is modeled using a **pi-equivalent circuit**. The key parameters for each branch from bus i to bus j are:

- **Series impedance**: z = r + jx (resistance + reactance), in per-unit
- **Series admittance**: y = 1/z = g + jb, where g = r/(r^2 + x^2) and b = -x/(r^2 + x^2)
- **Shunt charging susceptance**: bc (total line charging), in per-unit. Each end of the line gets bc/2.
- **Tap ratio**: t (dimensionless). For transformers, this is the turns ratio. For plain transmission lines, t = 1.0 (or stored as 0.0 in MATPOWER data, which must be treated as 1.0).
- **Phase shift**: theta_shift, in degrees (stored in data) but converted to radians for calculations.

### Branch Power Flow Equations

The power flowing from bus i to bus j (forward direction) is computed as follows. The active power is P_ij = g * Vm_i^2 / t^2 - (Vm_i * Vm_j / t) * (g * cos(delta) + b * sin(delta)), and the reactive power is Q_ij = -(b + bc/2) * Vm_i^2 / t^2 - (Vm_i * Vm_j / t) * (g * sin(delta) - b * cos(delta)), where delta = Va_i - Va_j - theta_shift.

The power flowing from bus j to bus i (reverse direction) is computed as follows. The active power is P_ji = g * Vm_j^2 - (Vm_i * Vm_j / t) * (g * cos(delta') + b * sin(delta')), and the reactive power is Q_ji = -(b + bc/2) * Vm_j^2 - (Vm_i * Vm_j / t) * (g * sin(delta') - b * cos(delta')), where delta' = Va_j - Va_i + theta_shift.

Note the critical asymmetry: the tap ratio t appears in the i-side terms (1/t^2 for the self term, 1/t for the mutual term) but does not appear in the j-side self term (Vm_j^2 coefficient is just g, not g/t^2). This reflects the physical placement of the transformer winding. Getting this asymmetry wrong is one of the most common implementation errors.

The **apparent power flow** in MVA at each end is the square root of the sum of squared active and reactive power, multiplied by baseMVA: S_ij = sqrt(P_ij^2 + Q_ij^2) * baseMVA and S_ji = sqrt(P_ji^2 + Q_ji^2) * baseMVA.

Note that S_ij and S_ji are generally not equal because the branch itself consumes (or occasionally generates) reactive power via its charging susceptance and dissipates active power via its resistance. The difference between forward and reverse apparent power flows is a consequence of losses in the branch.

### Branch Loading

A branch's **loading percentage** measures how close the maximum of its two directional flows is to the thermal limit. It is computed as the larger of the two directional apparent power flows divided by rateA, multiplied by 100: loading_pct = max(S_ij, S_ji) / rateA * 100.

Only branches with rateA > 0 have enforced flow limits. A branch with rateA = 0 is unconstrained.

## Nodal Power Balance

At each bus i, the **AC power balance** must hold. In per-unit, the active power balance requires that the sum of generator active outputs at bus i, minus the active demand, minus the shunt conductance term Gs_i * Vm_i^2, equals the sum of active branch flows out of bus i. The reactive power balance requires that the sum of generator reactive outputs at bus i, minus the reactive demand, plus the shunt susceptance term Bs_i * Vm_i^2, equals the sum of reactive branch flows out of bus i.

Key points about the balance equation:

- **Shunt elements** contribute Gs * Vm^2 to active power consumption (subtracted from generation) and Bs * Vm^2 to reactive power injection (added, not subtracted, on the generation side). The sign convention follows MATPOWER: positive Bs is capacitive (injects reactive power), positive Gs is resistive (consumes active power).
- **Multiple generators** at the same bus have their outputs summed.
- **Branch flows** are summed for all branches connected to bus i, using the appropriate direction (P_ij if i is the from-bus, P_ji if i is the to-bus).

## Generator Cost Function

Each generator has a quadratic cost function of the form Cost_k(Pg_k) = c2_k * Pg_k^2 + c1_k * Pg_k + c0_k, where Pg_k is in MW (not per-unit) and cost is in $/hr. The total system cost is the sum of all individual generator costs.

The MATPOWER gencost array encodes this as: [model, startup, shutdown, ncost, c2, c1, c0]. Model type 2 indicates polynomial cost. The cost coefficients are stored highest-order first (c2, c1, c0).

The objective of ACOPF is to minimize this total cost subject to all network constraints.

## MATPOWER Data Column Conventions

Understanding the column indexing of MATPOWER-format arrays is essential. All arrays are 0-indexed in JSON representation.

### Bus Array Columns

| Index | Field | Units | Description |
|-------|-------|-------|-------------|
| 0 | BUS_I | - | Bus number (1-indexed identifier) |
| 1 | BUS_TYPE | - | 1=PQ, 2=PV, 3=Slack |
| 2 | PD | MW | Real power demand |
| 3 | QD | MVAr | Reactive power demand |
| 4 | GS | MW at 1 pu V | Shunt conductance |
| 5 | BS | MVAr at 1 pu V | Shunt susceptance |
| 6 | BUS_AREA | - | Area number |
| 7 | VM | pu | Voltage magnitude (initial/setpoint) |
| 8 | VA | degrees | Voltage angle (initial) |
| 9 | BASE_KV | kV | Base voltage |
| 10 | ZONE | - | Loss zone |
| 11 | VMAX | pu | Maximum voltage magnitude |
| 12 | VMIN | pu | Minimum voltage magnitude |

### Generator Array Columns

| Index | Field | Units | Description |
|-------|-------|-------|-------------|
| 0 | GEN_BUS | - | Bus number where generator is connected |
| 1 | PG | MW | Real power output (initial) |
| 2 | QG | MVAr | Reactive power output (initial) |
| 3 | QMAX | MVAr | Maximum reactive power output |
| 4 | QMIN | MVAr | Minimum reactive power output |
| 5 | VG | pu | Voltage setpoint |
| 6 | MBASE | MVA | Machine MVA base |
| 7 | GEN_STATUS | - | 1=in-service, 0=out-of-service |
| 8 | PMAX | MW | Maximum real power output |
| 9 | PMIN | MW | Minimum real power output |

### Branch Array Columns

| Index | Field | Units | Description |
|-------|-------|-------|-------------|
| 0 | F_BUS | - | From bus number |
| 1 | T_BUS | - | To bus number |
| 2 | BR_R | pu | Resistance |
| 3 | BR_X | pu | Reactance |
| 4 | BR_B | pu | Total line charging susceptance |
| 5 | RATE_A | MVA | Long-term rating (thermal limit) |
| 6 | RATE_B | MVA | Short-term rating |
| 7 | RATE_C | MVA | Emergency rating |
| 8 | TAP | - | Transformer tap ratio (0 means 1.0) |
| 9 | SHIFT | degrees | Transformer phase shift angle |
| 10 | BR_STATUS | - | 1=in-service, 0=out-of-service |
| 11 | ANGMIN | degrees | Minimum angle difference (Va_from - Va_to) |
| 12 | ANGMAX | degrees | Maximum angle difference (Va_from - Va_to) |

### Generator Cost Array Columns

| Index | Field | Description |
|-------|-------|-------------|
| 0 | MODEL | Cost model type (2 = polynomial) |
| 1 | STARTUP | Startup cost ($) |
| 2 | SHUTDOWN | Shutdown cost ($) |
| 3 | NCOST | Number of cost coefficients |
| 4 | c2 | Quadratic cost coefficient ($/MW^2-hr) |
| 5 | c1 | Linear cost coefficient ($/MW-hr) |
| 6 | c0 | Constant cost term ($/hr) |

## The Complete ACOPF Formulation

The ACOPF problem has four sets of decision variables:

1. **Vm** (n_bus variables): Voltage magnitudes at each bus, bounded by [Vmin, Vmax]
2. **Va** (n_bus variables): Voltage angles at each bus, bounded by [-pi, pi]
3. **Pg** (n_gen variables): Active power output of each generator, bounded by [Pmin, Pmax]
4. **Qg** (n_gen variables): Reactive power output of each generator, bounded by [Qmin, Qmax]

The constraints are:

- **Power balance** (2 * n_bus equality constraints): Active and reactive balance at each bus
- **Reference angle** (1 equality constraint): Va = 0 at the slack bus
- **Branch flow limits** (up to 2 * n_branch inequality constraints): |S_ij|^2 <= rateA^2 and |S_ji|^2 <= rateA^2 for each branch with rateA > 0. Note: the constraint is applied in squared form to avoid square roots in the nonlinear program.
- **Angle difference bounds** (n_branch inequality constraints): angmin <= Va_from - Va_to <= angmax for each branch

This is a **nonconvex** nonlinear program (NLP) due to the trigonometric terms (cos, sin) in the power flow equations and the bilinear products of voltage magnitudes. Nonconvexity means:

- Multiple locally optimal solutions may exist
- Different solvers or starting points may find different feasible solutions
- There is no guarantee that a local optimum is the global optimum
- Two correct solutions to the same problem may have quite different generator dispatches and voltage profiles, yet both be equally valid if they are feasible and achieve similar cost

## Solving ACOPF

### Interior Point Methods (IPOPT)

IPOPT (Interior Point OPTimizer) is the standard solver for ACOPF. It handles large-scale nonlinear programs by maintaining a barrier function that keeps iterates away from constraint boundaries, then progressively reducing the barrier parameter to converge to a constrained optimum.

Key solver parameters that affect convergence:

- **Tolerance** (tol): Convergence tolerance on the KKT conditions. Typical values are 1e-6 to 1e-8.
- **Maximum iterations**: Safety bound to prevent infinite loops. 1000-2000 is usually sufficient.
- **mu_strategy**: "adaptive" is generally more robust than "monotone" for ACOPF.
- **Warm starting**: Providing good initial guesses (e.g., from a DC power flow or flat start) significantly affects convergence speed and which local optimum is found.

### Starting Points

Two common initialization strategies are:

- **Flat start**: Vm = 1.0 pu at all buses, Va = 0 at all buses, generators at midpoint of bounds. Simple and always available, but may converge slowly on stressed systems.
- **Data-based start**: Use the VM and VA columns from the bus data and PG/QG from the generator data. This is often closer to the solution but the values should still be clipped to variable bounds.

Running the solver from multiple starting points and taking the best result improves the chance of finding a good local minimum.

### Modeling Frameworks

CasADi is a widely used framework for formulating and solving NLPs. It provides:

- Symbolic variables (MX or SX types) for building expressions
- Automatic differentiation for computing gradients and Jacobians
- Direct interface to IPOPT for solving the resulting NLP
- Efficient sparse representations that scale to large networks

The typical workflow is: (1) define symbolic decision variables, (2) construct objective and constraint expressions symbolically, (3) assemble the NLP structure {x, f, g}, (4) set variable and constraint bounds, (5) call the solver.

## System-Level Accounting

### Losses

Total system losses are the difference between total generation and total load. That is, total losses in MW equal total generation in MW minus total load in MW.

Losses must be positive (generation exceeds load because power is dissipated in branch resistances). In typical transmission systems, losses are in the range of 1-5% of total load. Losses above 10% suggest a modeling or solver error.

### Generation Totals

The reported total generation must exactly equal the sum of individual generator outputs. This is a self-consistency check, not a power flow constraint. If the summary total does not match the sum of individual generators, the report has an arithmetic error.

### Feasibility Metrics

A feasible solution satisfies all constraints within numerical tolerance. Key feasibility metrics include:

- **Max P mismatch**: Largest active power balance violation across all buses (MW)
- **Max Q mismatch**: Largest reactive power balance violation across all buses (MVAr)
- **Max voltage violation**: Largest exceedance of voltage bounds (pu)
- **Max branch overload**: Largest exceedance of branch flow limits (MVA)

A well-converged solution should have all of these very close to zero.

## Why ACOPF Is Hard

Unlike the simpler DC approximation, ACOPF is a **nonconvex nonlinear program**. The trigonometric coupling between voltage magnitudes, angles, and power injections means that classical power flow methods (Gauss-Seidel, Newton-Raphson) only solve the power balance equations for a fixed dispatch — they do not minimize cost, and they struggle to converge on large or stressed networks where voltage and generation interact strongly.

In practice, ACOPF must be solved as a **monolithic optimization problem** where the objective and all constraints (power balance, voltage bounds, generator limits, branch flow limits, angle differences) are handled simultaneously by a nonlinear solver with access to exact gradients. Tools such as CasADi (symbolic modeling) paired with IPOPT (interior-point NLP solver), or other NLP frameworks, are commonly used for this purpose. Decomposing the problem into sequential steps (e.g., solving power flow first, then adjusting dispatch) loses the coupling information and typically produces infeasible or suboptimal results.

A well-converged ACOPF solution should exhibit nodal power balance residuals well below 1 MW at every bus when verified independently against the pi-model branch flow equations.

## Practical Considerations

### Tap Ratio Encoding Convention

In MATPOWER data, a tap ratio value of 0.0 represents a plain transmission line with an effective tap ratio of 1.0. This encoding convention means that any implementation must check for tap values of zero and treat them as unity. The zero value is a data encoding choice, not a physical parameter -- actual transformers with non-unity tap ratios store their true value in this field.

### Unit System Boundaries

The ACOPF formulation involves two unit systems that must be kept distinct. The rules governing unit usage are:

- Power flow equations use per-unit throughout
- Generator cost functions use Pg in MW (physical units)
- Branch flow limits (rateA) are stored in MVA and must be converted to per-unit before comparing with per-unit flow calculations
- Bus loads and shunts are stored in MW/MVAr and must be converted to per-unit
- Branch impedances and susceptances are already stored in per-unit

### Shunt Element Sign Convention

In the reactive power balance, shunt susceptance (Bs) contributes with a **positive sign** (Bs * Vm^2 injects reactive power), while shunt conductance (Gs) contributes with a **negative sign** effectively (Gs * Vm^2 consumes active power). The MATPOWER convention is that positive Bs is capacitive and positive Gs is resistive.

### Transformer Model Asymmetry

The pi-model branch equations are inherently asymmetric when the tap ratio differs from 1.0. The from-side (tap side) carries the 1/t^2 scaling on the self-admittance term, while the to-side does not. This asymmetry reflects the physical placement of the transformer winding and is a fundamental property of the model.

### Angle Unit Conventions

Branch angle limits (angmin, angmax) and the phase shift angle are stored in **degrees** in MATPOWER data. All trigonometric calculations in the power flow equations require these values in **radians**. Voltage angles are typically computed in radians internally but reported in degrees in output summaries.

### Branch Flow Limit Formulation

The apparent power constraint is formulated as |S|^2 <= rateA^2, using the squared form to avoid a square root in the nonlinear program. This is mathematically equivalent to |S| <= rateA but produces better-behaved derivatives for the solver. Only branches with rateA > 0 have enforced limits; branches with rateA = 0 are unconstrained.

### Bus Identifier Mapping

Bus numbers in MATPOWER data are not necessarily contiguous or 0-indexed. A network might have bus numbers {1, 5, 17, 300}. All internal array indexing (voltage arrays, power injection arrays) uses a contiguous 0-based index, so a bus-ID-to-index mapping must be maintained. Generator and branch data reference buses by their MATPOWER bus number, not by array index.

### Generator Numbering Convention

In output reports, generators are numbered 1 through n_gen (1-indexed), corresponding to their order in the gen array (0-indexed internally). The bus field in the generator report contains the MATPOWER bus number, not the internal array index.

### Nonconvexity and Solution Variability

Because ACOPF is nonconvex, different locally optimal solutions may have significantly different dispatch patterns and costs. A solution is considered acceptable if it is feasible (satisfies all constraints) and its total cost is within a reasonable range of the best known solution. Two valid solutions to the same network may disagree on individual generator outputs while both being correct.

### Cost Function Evaluation in Physical Units

The cost must be computed using the polynomial cost coefficients applied to Pg in MW (not per-unit). The total cost is the sum of individual generator costs. The reported total cost per hour in the summary must match the sum recomputed from the cost coefficients and reported generator outputs. Consistency between the summary total and the individual generator costs serves as a self-check on the solution.

### Report Self-Consistency and Rounding

Use one clearly defined set of physical quantities as the source of truth for
costs, feasibility checks, summaries, and rankings. Numerical optimization and
constraint checks normally retain solver precision until serialization; any
display rounding policy should be explicit and applied consistently. Validate
that serialized values remain within declared tolerances, and use a stable
secondary key when nearly equal ranking values require deterministic ordering.

Ranking code should compute the complete eligible population, apply a stable
descending sort, and only then select a presentation subset.  The subset size
is part of an output contract, not an electrical property, so reusable code
should accept it as a parameter rather than hard-code an arbitrary value.  Read
an exact cardinality from the current instruction, schema, or another supplied
contract when one is present; otherwise preserve the full ranking or make the
chosen reporting policy explicit.  A deterministic secondary key is useful
when two rounded loading values tie.
