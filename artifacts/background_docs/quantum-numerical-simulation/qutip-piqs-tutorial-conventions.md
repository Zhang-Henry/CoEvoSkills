# QuTiP PIQS open-Dicke tutorial conventions

When reproducing a published numerical tutorial, use its parameterization as a
single coherent software convention.  In QuTiP's public “Superradiance: Open
Dicke Model” PIQS example, the photon cutoff variable is passed directly as the
dimension of `destroy`, the collective operator is the PIQS `Jx`, and the
interaction is implemented in the form

```python
h_int = g * tensor(a + a.dag(), jx)
```

Do not multiply that tutorial coefficient by a second factor of two.  The
identity `J+ + J- = 2 Jx` is correct, but translating an independently written
ladder-operator Hamiltonian into a `Jx` Hamiltonian also translates the
coefficient.  Mixing the coefficient from one convention with the operator
from the other changes the physical model.

Build the spin Liouvillian with the PIQS `Dicke` rate interface, including the
spin Hamiltonian once.  Build the cavity Hamiltonian and cavity-loss
Liouvillian in photon space.  Promote identities to superoperators, combine
the cavity and spin Liouvillians with `super_tensor`, and add the interaction
commutator once with `spre` and `spost`.  Keep the cavity as subsystem zero if
the later partial trace uses index zero.

Before the expensive grid, validate a small instance for dimensions, trace,
Hermiticity, steady-state residual, subsystem ordering, and Wigner
normalization.  Then compute the Wigner function from the reduced cavity state
and validate every serialized grid for shape, finiteness, axis ordering,
normalization, and distinctness.  These checks detect convention drift without
using reference output values.

Public source: QuTiP PIQS, “Superradiance: Open Dicke Model.”
