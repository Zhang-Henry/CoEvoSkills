# General Background for JAX Numerical Programs

This note summarizes public JAX concepts. It does not enumerate the computations, inputs, archive keys, shapes, or expected outputs of any supplied task set.

## Arrays and functional computation

JAX offers a NumPy-like array API together with program transformations. JAX arrays are immutable: updates produce new values instead of mutating an array in place. Dtypes and shapes remain important, especially because numerical defaults and accelerator behavior may differ from a conventional NumPy program.

Array reductions remove the axes named by the operation. Broadcasting applies elementwise operations across compatible shapes. Matrix multiplication requires agreement of inner dimensions, so inspecting runtime shapes is a basic correctness check.

## Core transformations

- Vectorized mapping lifts a function written for one example so it can operate over a chosen batch axis.
- Automatic differentiation computes derivatives of functions; the basic gradient transform expects a scalar-valued result.
- Structured scan represents repeated state transitions with an explicit carry and a sequence of outputs.
- Just-in-time compilation traces a function and compiles it for the observed abstract shapes and dtypes.

Transformed functions work best when computation is expressed with array operations and explicit functional state. Python mutation and value-dependent Python control flow can conflict with tracing. JAX supplies control-flow primitives for cases where branching or iteration must depend on traced values.

## Data handling and verification

Numerical task bundles may use a single-array file or a named multi-array archive. The file type, available keys, shapes, and dtypes should be inspected at runtime rather than assumed. Results should be written to the exact public destination in a standard array format that downstream NumPy-compatible readers can load.

A reliable implementation checks each task description independently, validates output shape and dtype, compares small calculations against an untransformed formulation when practical, and ensures device arrays have been materialized before the process exits. Compilation success alone does not prove that axes, operands, archive members, or recurrence semantics are correct.

The choice between broadcasting, vectorized mapping, differentiation, scan, and compilation follows from the computation described by the current task. Background examples should not substitute for discovering that computation from the supplied task manifest and data.
