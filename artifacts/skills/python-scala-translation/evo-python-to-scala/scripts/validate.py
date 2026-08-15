"""Validation utilities for Python-to-Scala translations.

Provides functions to validate that a Scala translation meets
quality and correctness requirements.
"""

import os
import re
import subprocess
from typing import Dict, List, Tuple, Optional


def validate_scala_file(scala_path: str) -> Dict[str, object]:
    """Validate a Scala file for common issues.
    
    Returns a dict with validation results.
    """
    results = {
        'exists': False,
        'has_package': False,
        'has_imports': False,
        'line_count': 0,
        'issues': []
    }
    
    if not os.path.exists(scala_path):
        results['issues'].append(f'File not found: {scala_path}')
        return results
    
    results['exists'] = True
    
    with open(scala_path, 'r') as f:
        content = f.read()
    
    lines = content.splitlines()
    results['line_count'] = len(lines)
    
    # Check package declaration
    results['has_package'] = any(line.strip().startswith('package ') for line in lines)
    if not results['has_package']:
        results['issues'].append('Missing package declaration')
    
    # Check imports
    results['has_imports'] = any(line.strip().startswith('import ') for line in lines)
    
    # Check for Python-isms that shouldn't be in Scala
    python_isms = [
        (r'\bdef\s+\w+_\w+\s*\(', 'snake_case method name found (should be camelCase)'),
        (r'\bNone\b(?!\s*=>)', 'Python None found (should be Scala None or Option.empty)'),
        (r'\bTrue\b', 'Python True found (should be Scala true)'),
        (r'\bFalse\b', 'Python False found (should be Scala false)'),
        (r'\bself\b', 'Python self found (should be this or omitted)'),
        (r'\bprint\s*\(', 'print() found (should be println)'),
    ]
    
    for pattern, msg in python_isms:
        # Search in non-comment, non-string lines
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('*'):
                continue
            if re.search(pattern, stripped):
                # Exclude false positives in string literals
                if '"' + pattern.replace('\\b', '') + '"' not in stripped:
                    results['issues'].append(f'Line {i}: {msg}')
                    break
    
    # Check for common Scala best practices
    if 'sealed trait' not in content and 'sealed abstract' not in content:
        if 'Enum' in content or 'enum' in content.lower():
            results['issues'].append('Missing sealed trait for ADT/enum pattern')
    
    if 'case class' not in content:
        results['issues'].append('No case classes found (expected for immutable data)')
    
    # Check variance annotations if generics are used
    if '[T]' in content or '[A]' in content:
        # Generics exist, check if variance is used where appropriate
        pass  # This is hard to check statically without full context
    
    results['valid'] = len(results['issues']) == 0
    return results


def validate_compilation(scala_path: str, localtest_dir: str) -> Tuple[bool, str]:
    """Validate that the Scala file compiles in the sbt project."""
    import shutil
    
    target = os.path.join(localtest_dir, 'src/main/scala/tokenizer/Tokenizer.scala')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(scala_path, target)
    
    result = subprocess.run(
        ['sbt', 'compile'],
        cwd=localtest_dir,
        capture_output=True,
        text=True,
        timeout=120
    )
    output = result.stdout + result.stderr
    success = result.returncode == 0 and '[success]' in output
    return success, output


def validate_tests(localtest_dir: str) -> Tuple[bool, int, int, str]:
    """Run tests and return (all_passed, num_passed, num_failed, output)."""
    result = subprocess.run(
        ['sbt', 'test'],
        cwd=localtest_dir,
        capture_output=True,
        text=True,
        timeout=180
    )
    output = result.stdout + result.stderr
    all_passed = result.returncode == 0 and 'All tests passed' in output
    
    passed_match = re.search(r'succeeded (\d+)', output)
    failed_match = re.search(r'failed (\d+)', output)
    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    
    return all_passed, passed, failed, output


def full_validation(
    scala_path: str,
    localtest_dir: Optional[str] = None,
    required_classes: Optional[List[str]] = None,
    required_methods: Optional[List[str]] = None
) -> Dict[str, object]:
    """Complete validation pipeline.
    
    Args:
        scala_path: Path to the Scala source file
        localtest_dir: Path to sbt project for compilation/test validation
        required_classes: Class/trait/object names that must be present
        required_methods: Method names that must be present (camelCase)
    
    Returns:
        Dict with all validation results
    """
    results = {'overall_success': False}
    
    # Static validation
    static = validate_scala_file(scala_path)
    results['static'] = static
    
    if not static['exists']:
        return results
    
    # Check required elements
    with open(scala_path, 'r') as f:
        content = f.read()
    
    if required_classes:
        from translate import extract_scala_classes
        found_classes = extract_scala_classes(content)
        missing = [c for c in required_classes if c not in found_classes]
        results['missing_classes'] = missing
    else:
        missing = []
        results['missing_classes'] = []
    
    if required_methods:
        from translate import extract_scala_methods
        found_methods = extract_scala_methods(content)
        missing_m = [m for m in required_methods if m not in found_methods]
        results['missing_methods'] = missing_m
    else:
        missing_m = []
        results['missing_methods'] = []
    
    # Compilation and test validation
    if localtest_dir and os.path.isdir(localtest_dir):
        comp_ok, comp_output = validate_compilation(scala_path, localtest_dir)
        results['compilation'] = {'success': comp_ok}
        
        if comp_ok:
            test_ok, passed, failed, test_output = validate_tests(localtest_dir)
            results['tests'] = {
                'success': test_ok,
                'passed': passed,
                'failed': failed
            }
            results['overall_success'] = test_ok and len(missing) == 0 and len(missing_m) == 0
        else:
            results['compilation']['errors'] = comp_output[-1000:]
            results['overall_success'] = False
    else:
        results['overall_success'] = static.get('valid', False) and len(missing) == 0 and len(missing_m) == 0
    
    return results
