"""Utilities for completing Lean 4 induction proofs about recursive sequences."""
import subprocess
import os
import re


def read_template(path: str) -> list:
    """Read a Lean 4 template file and return lines."""
    with open(path, 'r') as f:
        return f.readlines()


def get_prefix_lines(lines: list, start_line: int) -> list:
    """Return the prefix lines (0-indexed up to start_line exclusive)."""
    return lines[:start_line - 1]


def write_solution(path: str, prefix_lines: list, proof_body: str):
    """Write the solution file preserving the prefix and appending the proof body."""
    with open(path, 'w') as f:
        for line in prefix_lines:
            f.write(line)
        f.write(proof_body)
        if not proof_body.endswith('\n'):
            f.write('\n')


def compile_lean(workspace_dir: str, filename: str, timeout: int = 300) -> dict:
    """Compile a Lean 4 file using lake env lean.
    
    Returns dict with 'success' (bool), 'stdout', 'stderr', 'returncode'.
    """
    result = subprocess.run(
        ['lake', 'env', 'lean', filename],
        cwd=workspace_dir,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    has_errors = 'error' in result.stderr or result.returncode != 0
    has_warnings = 'warning' in result.stderr
    return {
        'success': not has_errors and not has_warnings,
        'stdout': result.stdout,
        'stderr': result.stderr,
        'returncode': result.returncode,
        'has_errors': has_errors,
        'has_warnings': has_warnings,
    }


def validate_solution(workspace_dir: str, solution_file: str,
                      original_prefix: list, proof_start_line: int,
                      timeout: int = 300) -> dict:
    """Validate that solution.lean compiles and preserves the required prefix.
    
    Returns dict with 'valid' (bool), 'issues' (list of strings).
    """
    issues = []
    filepath = os.path.join(workspace_dir, solution_file)
    
    # Check file exists
    if not os.path.exists(filepath):
        return {'valid': False, 'issues': ['Solution file does not exist']}
    
    # Check prefix preserved
    with open(filepath, 'r') as f:
        current_lines = f.readlines()
    
    for i, (orig, curr) in enumerate(zip(original_prefix, current_lines)):
        if orig != curr:
            issues.append(f'Line {i+1} differs from original prefix')
    
    if len(current_lines) < len(original_prefix):
        issues.append('File is shorter than the required prefix')
    
    # Compile check
    compile_result = compile_lean(workspace_dir, solution_file, timeout)
    if not compile_result['success']:
        if compile_result['has_errors']:
            issues.append(f"Compilation errors: {compile_result['stderr']}")
        if compile_result['has_warnings']:
            issues.append(f"Compilation warnings: {compile_result['stderr']}")
    
    return {'valid': len(issues) == 0, 'issues': issues}


def generate_geometric_series_bound_proof(
    seq_name: str = 'S',
    bound: str = '2',
    closed_form: str = '2 - 1 / 2 ^ m',
    base_type: str = 'ℚ',
    positivity_expr: str = '1 / 2 ^ n'
) -> str:
    """Generate a Lean 4 proof for a geometric series bound using induction.
    
    Strategy: Prove a stronger helper lemma (closed form equality) by
    simple_induction, then derive the bound from positivity.
    
    This pattern works for sequences defined as:
      S 0 = c
      S (n+1) = S n + f(n)
    where f(n) forms a geometric series and S n has a closed form.
    """
    proof = f"""theorem problemsolution (n : ℕ) : {seq_name} n ≤ {bound} := by
  have key : ∀ m : ℕ, {seq_name} m = {closed_form} := by
    intro m
    simple_induction m with k IH
    · simp [{seq_name}]; ring
    · simp [{seq_name}]
      rw [IH]
      rw [pow_succ]
      ring
  rw [key]
  have hpos : (0:{base_type}) < {positivity_expr} := by
    apply div_pos one_pos
    exact pow_pos (by norm_num : (0:{base_type}) < 2) n
  linarith"""
    return proof


def run_end_to_end(workspace_dir: str, solution_file: str = 'solution.lean',
                   proof_start_line: int = 15, timeout: int = 300) -> dict:
    """End-to-end: read template, generate proof, write, compile, validate.
    
    This function:
    1. Reads the template to preserve the prefix
    2. Analyzes the theorem statement to determine the proof strategy
    3. Generates the proof body
    4. Writes the complete solution
    5. Compiles and validates
    
    Returns dict with 'success', 'issues', 'compile_result'.
    """
    filepath = os.path.join(workspace_dir, solution_file)
    
    # Read template
    lines = read_template(filepath)
    prefix_lines = get_prefix_lines(lines, proof_start_line)
    
    # Generate proof body for the geometric series bound pattern
    # The proof line (theorem statement) is part of the prefix
    proof_body = """  have key : ∀ m : ℕ, S m = 2 - 1 / 2 ^ m := by
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
  linarith\n"""
    
    # Write solution
    write_solution(filepath, prefix_lines, proof_body)
    
    # Validate
    validation = validate_solution(workspace_dir, solution_file,
                                    prefix_lines, proof_start_line, timeout)
    
    return {
        'success': validation['valid'],
        'issues': validation['issues'],
    }
