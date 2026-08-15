"""Python-to-Scala translation utilities.

Provides functions for analyzing Python source code and generating
idiomatic Scala 2.13 translations, following the conventions described
in the background document.
"""

import ast
import os
import re
import subprocess
import textwrap
from typing import List, Dict, Optional, Tuple


# ============================================================================
# Python AST Analysis Utilities
# ============================================================================

def extract_python_classes(source: str) -> List[str]:
    """Extract class names from Python source code."""
    tree = ast.parse(source)
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def extract_python_functions(source: str) -> List[str]:
    """Extract top-level function names from Python source code."""
    tree = ast.parse(source)
    return [node.name for node in ast.iter_child_nodes(tree) if isinstance(node, ast.FunctionDef)]


def extract_class_methods(source: str, class_name: str) -> List[str]:
    """Extract method names from a specific class."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
    return []


def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase (Scala convention for methods/vals)."""
    parts = name.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase (Scala convention for types/classes)."""
    return ''.join(p.capitalize() for p in name.split('_'))


# ============================================================================
# Scala Code Analysis
# ============================================================================

def extract_scala_classes(scala_source: str) -> List[str]:
    """Extract class/trait/object names from Scala source."""
    pattern = r'(?:class|trait|object|case class|case object)\s+(\w+)'
    return re.findall(pattern, scala_source)


def extract_scala_methods(scala_source: str) -> List[str]:
    """Extract def method names from Scala source."""
    pattern = r'\bdef\s+(\w+)'
    return re.findall(pattern, scala_source)


# ============================================================================
# Translation Pattern Checklist
# ============================================================================

def check_translation_patterns(python_source: str, scala_source: str) -> Dict[str, bool]:
    """Check that key translation patterns have been applied.
    
    Returns a dict of pattern_name -> whether it was found in the Scala output.
    """
    checks = {}
    
    # Enum -> sealed trait
    has_python_enum = 'class' in python_source and '(Enum)' in python_source
    if has_python_enum:
        checks['enum_to_sealed_trait'] = 'sealed trait' in scala_source
    
    # dataclass -> case class
    has_dataclass = '@dataclass' in python_source
    if has_dataclass:
        checks['dataclass_to_case_class'] = 'case class' in scala_source
    
    # Protocol -> type class
    has_protocol = 'Protocol' in python_source
    if has_protocol:
        checks['protocol_to_typeclass'] = 'trait' in scala_source and 'implicit' in scala_source
    
    # Optional -> Option
    has_optional = 'Optional' in python_source or '| None' in python_source
    if has_optional:
        checks['optional_to_option'] = 'Option[' in scala_source
    
    # snake_case -> camelCase methods
    py_methods = re.findall(r'def (\w+_\w+)', python_source)
    if py_methods:
        scala_methods = extract_scala_methods(scala_source)
        camel_versions = [snake_to_camel(m) for m in py_methods if not m.startswith('_')]
        found = sum(1 for c in camel_versions if c in scala_methods)
        checks['snake_to_camel_naming'] = found > 0
    
    # Generic variance annotations
    has_covariant = 'covariant=True' in python_source or 'T_co' in python_source
    if has_covariant:
        checks['covariance_annotation'] = '[+' in scala_source
    
    has_contravariant = 'contravariant=True' in python_source or 'T_contra' in python_source
    if has_contravariant:
        checks['contravariance_annotation'] = '[-' in scala_source
    
    # Immutable collections default
    checks['immutable_collections'] = 'Map.empty' in scala_source or 'Map(' in scala_source
    
    # Package declaration
    checks['has_package'] = scala_source.strip().startswith('package ')
    
    # No null usage in public API
    # (null may appear in getOrElse null-check which is acceptable)
    checks['no_public_null'] = scala_source.count('null') <= 2  # Allow limited internal use
    
    return checks


# ============================================================================
# Required Elements Verification
# ============================================================================

def verify_required_elements(
    scala_source: str,
    required_classes: List[str],
    required_methods: List[str]
) -> Tuple[List[str], List[str]]:
    """Verify that all required classes and methods exist in the Scala source.
    
    Returns (missing_classes, missing_methods).
    """
    scala_classes = extract_scala_classes(scala_source)
    scala_methods = extract_scala_methods(scala_source)
    
    missing_classes = [c for c in required_classes if c not in scala_classes]
    missing_methods = [m for m in required_methods if m not in scala_methods]
    
    return missing_classes, missing_methods


# ============================================================================
# Compilation and Testing
# ============================================================================

def compile_scala(scala_file: str, localtest_dir: str) -> Tuple[bool, str]:
    """Copy Scala file to localtest dir and compile with sbt.
    
    Returns (success, output_text).
    """
    import shutil
    target = os.path.join(localtest_dir, 'src/main/scala/tokenizer/Tokenizer.scala')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(scala_file, target)
    
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


def run_tests(localtest_dir: str) -> Tuple[bool, str, int, int]:
    """Run sbt tests and return (success, output, passed, failed)."""
    result = subprocess.run(
        ['sbt', 'test'],
        cwd=localtest_dir,
        capture_output=True,
        text=True,
        timeout=180
    )
    output = result.stdout + result.stderr
    success = result.returncode == 0 and 'All tests passed' in output
    
    passed_match = re.search(r'succeeded (\d+)', output)
    failed_match = re.search(r'failed (\d+)', output)
    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    
    return success, output, passed, failed


# ============================================================================
# End-to-End Entry Point
# ============================================================================

def translate_and_validate(
    python_input_path: str,
    scala_output_path: str,
    localtest_dir: Optional[str] = None,
    required_classes: Optional[List[str]] = None,
    required_methods: Optional[List[str]] = None
) -> Dict[str, object]:
    """End-to-end translation pipeline.
    
    This function:
    1. Reads the Python source
    2. Analyzes it to understand structure
    3. Writes the Scala translation (the Scala content must be provided
       or already exist at scala_output_path)
    4. Validates the translation against requirements
    5. Optionally compiles and tests
    
    NOTE: The actual Scala code generation is a creative/intellectual task
    that requires understanding the Python semantics. This function provides
    the scaffolding: analysis, validation, compilation, and testing.
    The Scala source file should be written by the agent following the
    translation patterns documented in SKILL.md.
    
    Args:
        python_input_path: Path to the Python source file
        scala_output_path: Path where the Scala file is/will be
        localtest_dir: Optional path to sbt project for compilation testing
        required_classes: List of class/trait/object names that must exist
        required_methods: List of method names that must exist
    
    Returns:
        Dict with analysis results, validation status, and test results
    """
    results = {
        'python_analysis': {},
        'validation': {},
        'compilation': None,
        'tests': None,
        'success': False
    }
    
    # 1. Read and analyze Python source
    with open(python_input_path, 'r') as f:
        python_source = f.read()
    
    py_classes = extract_python_classes(python_source)
    py_functions = extract_python_functions(python_source)
    results['python_analysis'] = {
        'classes': py_classes,
        'functions': py_functions,
        'lines': len(python_source.splitlines())
    }
    
    # 2. Read Scala source (must already exist)
    if not os.path.exists(scala_output_path):
        results['validation']['error'] = f'Scala file not found at {scala_output_path}'
        return results
    
    with open(scala_output_path, 'r') as f:
        scala_source = f.read()
    
    # 3. Check translation patterns
    pattern_checks = check_translation_patterns(python_source, scala_source)
    results['validation']['patterns'] = pattern_checks
    
    # 4. Check required elements
    req_classes = required_classes or []
    req_methods = required_methods or []
    missing_classes, missing_methods = verify_required_elements(
        scala_source, req_classes, req_methods
    )
    results['validation']['missing_classes'] = missing_classes
    results['validation']['missing_methods'] = missing_methods
    
    # 5. Compile if localtest_dir provided
    if localtest_dir and os.path.isdir(localtest_dir):
        comp_success, comp_output = compile_scala(scala_output_path, localtest_dir)
        results['compilation'] = {
            'success': comp_success,
            'output_tail': comp_output[-500:] if len(comp_output) > 500 else comp_output
        }
        
        if comp_success:
            test_success, test_output, passed, failed = run_tests(localtest_dir)
            results['tests'] = {
                'success': test_success,
                'passed': passed,
                'failed': failed,
                'output_tail': test_output[-500:] if len(test_output) > 500 else test_output
            }
            results['success'] = test_success
        else:
            results['success'] = False
    else:
        # Without compilation, success is based on pattern checks
        all_patterns_ok = all(pattern_checks.values())
        no_missing = len(missing_classes) == 0 and len(missing_methods) == 0
        results['success'] = all_patterns_ok and no_missing
    
    return results
