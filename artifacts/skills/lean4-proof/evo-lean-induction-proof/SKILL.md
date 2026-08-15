---
name: evo-lean-induction-proof
description: "Completes Lean 4 induction proofs for recursive sequence bounds. Use when a task requires proving an inequality about a recursively defined sequence (e.g., geometric series partial sums) in Lean 4 with the Math2001/Macbeth library tactics (simple_induction, addarith, numbers, extra). Provides end-to-end proof generation, compilation, and validation."
---

# Lean 4 Induction Proof Skill

## Overview

This skill handles Lean 4 proof completion tasks where:
- A recursive sequence is defined (e.g., partial sums of a geometric series)
- A bound must be proved for all natural numbers
- The proof environment uses Heather Macbeth's Math2001 library tactics

## Key Proof Strategy

**Stronger Helper Lemma Pattern:**
When proving `S n ≤ bound` for a recursive sequence, direct induction often
fails because the inductive hypothesis `S k ≤ bound` is too weak. Instead:

1. Find the closed-form expression for S n (e.g., `S n = 2 - 1/2^n`)
2. Prove `S m = closed_form` by `simple_induction`
3. Rewrite the goal with the closed form
4. Prove the bound using positivity of the remainder term

**Tactic Reference (Math2001 library):**
- `simple_induction n with k IH` — standard induction with push_cast
- `simp [S]` — unfold the recursive definition
- `rw [IH]` — apply induction hypothesis
- `rw [pow_succ]` — rewrite `2^(k+1)` as `2^k * 2`
- `ring` — close algebraic goals over commutative rings
- `norm_num` — numeric normalization
- `linarith` — linear arithmetic
- `addarith` — weaker linear arithmetic (from library)
- `positivity` — prove positivity goals (from Mathlib)
- `div_pos`, `pow_pos` — positivity lemmas for division and powers

**Compilation:**
- Use `lake env lean solution.lean` (not `lean` directly, not `lake build`)
- No output = success; any output indicates errors or warnings
- Warnings must be treated as errors (remove unused variables)
- Avoid `field_simp` — may not be available in all configurations

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-lean-induction-proof/scripts')
from utils import run_end_to_end, validate_solution, read_template, get_prefix_lines, write_solution, compile_lean

# End-to-end: reads template, generates proof, writes, compiles, validates
result = run_end_to_end(
    workspace_dir='/app/workspace',
    solution_file='solution.lean',
    proof_start_line=15,  # line where proof body starts
    timeout=300
)
print(f"Success: {result['success']}")
if not result['success']:
    print(f"Issues: {result['issues']}")

# Validation only (after manual proof writing)
lines = read_template('/app/workspace/solution.lean')
prefix = get_prefix_lines(lines, 15)
val = validate_solution('/app/workspace', 'solution.lean', prefix, 15)
print(f"Valid: {val['valid']}, Issues: {val['issues']}")
```

## Proof Template

For a sequence `S` with `S 0 = 1` and `S (n+1) = S n + 1/2^(n+1)`:

```lean
theorem problemsolution (n : ℕ) : S n ≤ 2 := by
  have key : ∀ m : ℕ, S m = 2 - 1 / 2 ^ m := by
    intro m
    simple_induction m with k IH
    · simp [S]; ring
    · simp [S]
      rw [IH]
      rw [pow_succ]
      ring
  rw [key]
  have hpos : (0:ℚ) < 1 / 2 ^ n := by
    apply div_pos one_pos
    exact pow_pos (by norm_num : (0:ℚ) < 2) n
  linarith
```

## Key Insights

1. **push_cast interaction**: `simple_induction` calls `push_cast` which changes
   `1/2^n` to `(2^n)⁻¹` notation. Using `simp [S]` followed by `rw [IH]` and
   `ring` handles this cleanly.

2. **pow_succ direction**: `pow_succ 2 k` rewrites `2^(k+1)` as `2^k * 2`.
   After `rw [pow_succ]`, `ring` can close the algebraic identity.

3. **Avoiding unused variables**: The lakefile may set `-DwarningAsError=false`
   but the task constraint says treat warnings as errors. Remove any `have`
   statements that aren't used in the proof.

4. **No field_simp**: This tactic may not be available. Use `div_pos`, `ring`,
   and manual rewrites instead.
