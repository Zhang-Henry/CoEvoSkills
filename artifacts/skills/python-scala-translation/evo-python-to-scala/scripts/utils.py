"""Utility functions for Python-to-Scala translation tasks."""

import os
import subprocess
import re


def read_python_source(path: str) -> str:
    """Read Python source file."""
    with open(path, 'r') as f:
        return f.read()


def write_scala_source(path: str, content: str) -> None:
    """Write Scala source file."""
    with open(path, 'w') as f:
        f.write(content)


def extract_python_classes(source: str) -> list:
    """Extract class names from Python source."""
    return re.findall(r'^class\s+(\w+)', source, re.MULTILINE)


def extract_python_functions(source: str) -> list:
    """Extract top-level function names from Python source."""
    return re.findall(r'^def\s+(\w+)', source, re.MULTILINE)


def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def setup_sbt_project(root_dir: str, scala_file: str, package_name: str) -> str:
    """Set up sbt project structure for compilation.
    
    Returns path to the scala file in src directory.
    """
    src_dir = os.path.join(root_dir, 'src', 'main', 'scala', package_name)
    os.makedirs(src_dir, exist_ok=True)
    
    project_dir = os.path.join(root_dir, 'project')
    os.makedirs(project_dir, exist_ok=True)
    
    props_file = os.path.join(project_dir, 'build.properties')
    if not os.path.exists(props_file):
        with open(props_file, 'w') as f:
            f.write('sbt.version=1.9.7\n')
    
    dest = os.path.join(src_dir, os.path.basename(scala_file))
    return dest


def compile_scala(root_dir: str, scala_file: str, package_name: str) -> dict:
    """Compile Scala file using sbt.
    
    Handles the duplicate file issue by temporarily moving the root-level
    scala file and compiling from src/main/scala.
    
    Returns dict with 'success', 'stdout', 'stderr' keys.
    """
    import shutil
    
    dest = setup_sbt_project(root_dir, scala_file, package_name)
    
    # Copy to src location
    shutil.copy2(scala_file, dest)
    
    # Temporarily rename root-level file to avoid duplicate compilation
    bak_file = scala_file + '.bak'
    root_file_exists = os.path.exists(scala_file) and os.path.abspath(scala_file) != os.path.abspath(dest)
    
    if root_file_exists:
        os.rename(scala_file, bak_file)
    
    try:
        result = subprocess.run(
            ['sbt', 'compile'],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
    finally:
        # Restore root-level file
        if root_file_exists and os.path.exists(bak_file):
            shutil.copy2(dest, scala_file)
            os.remove(bak_file)


def validate_required_elements(scala_source: str, required_names: list) -> dict:
    """Validate that required classes/functions exist in Scala source.
    
    Returns dict with 'missing' list and 'found' list.
    """
    found = []
    missing = []
    
    for name in required_names:
        # Check for class, object, trait, def, or case class/object
        patterns = [
            rf'\b(class|object|trait)\s+{re.escape(name)}\b',
            rf'\bdef\s+{re.escape(name)}\b',
            rf'\bcase\s+(class|object)\s+{re.escape(name)}\b',
        ]
        if any(re.search(p, scala_source) for p in patterns):
            found.append(name)
        else:
            missing.append(name)
    
    return {'found': found, 'missing': missing}


def run_end_to_end(python_file: str, scala_output: str, package_name: str,
                   required_names: list, root_dir: str = '/root') -> dict:
    """End-to-end: read Python, write Scala, compile, validate.
    
    Note: This function assumes the Scala source has already been written
    to scala_output. It validates and compiles.
    """
    results = {'steps': []}
    
    # Step 1: Read and validate Scala source
    scala_source = read_python_source(scala_output)  # reuse reader
    
    # Step 2: Check required elements
    validation = validate_required_elements(scala_source, required_names)
    results['validation'] = validation
    results['steps'].append(f"Validation: found={len(validation['found'])}, missing={len(validation['missing'])}")
    
    if validation['missing']:
        results['success'] = False
        results['error'] = f"Missing required elements: {validation['missing']}"
        return results
    
    # Step 3: Check package declaration
    if f'package {package_name}' not in scala_source:
        results['success'] = False
        results['error'] = f"Missing package declaration: package {package_name}"
        return results
    results['steps'].append('Package declaration found')
    
    # Step 4: Compile
    compile_result = compile_scala(root_dir, scala_output, package_name)
    results['compilation'] = compile_result
    results['steps'].append(f"Compilation: {'success' if compile_result['success'] else 'failed'}")
    results['success'] = compile_result['success']
    
    return results


def validate_deliverable(scala_output: str, package_name: str, required_names: list) -> dict:
    """Validate the Scala deliverable without recompiling."""
    scala_source = read_python_source(scala_output)
    
    issues = []
    
    # Check package
    if f'package {package_name}' not in scala_source:
        issues.append(f'Missing package declaration: package {package_name}')
    
    # Check required elements
    validation = validate_required_elements(scala_source, required_names)
    if validation['missing']:
        issues.append(f"Missing elements: {validation['missing']}")
    
    # Check Scala conventions
    # 2-space indentation (check first indented line)
    lines = scala_source.split('\n')
    four_space_lines = sum(1 for l in lines if l.startswith('    ') and not l.startswith('      '))
    two_space_lines = sum(1 for l in lines if l.startswith('  ') and not l.startswith('    '))
    if four_space_lines > two_space_lines:
        issues.append('Uses 4-space indentation instead of 2-space (Scala convention)')
    
    # Check for null usage (anti-pattern in Scala)
    null_uses = len(re.findall(r'\bnull\b', scala_source))
    if null_uses > 2:  # Allow minimal null for JVM interop
        issues.append(f'Excessive null usage ({null_uses} occurrences) - use Option instead')
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'line_count': len(lines),
        'found_elements': validation['found']
    }
