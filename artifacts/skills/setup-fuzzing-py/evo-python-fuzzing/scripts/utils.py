"""Utility functions for setting up coverage-guided Python fuzzing with Atheris."""

import os
import subprocess
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple


def discover_libraries(base_dir: str) -> List[str]:
    """Discover Python library directories under base_dir.
    
    A directory is considered a library if it contains pyproject.toml or setup.py.
    Returns sorted list of absolute paths.
    """
    base = Path(base_dir)
    libs = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith('.') or entry.name == 'environment':
            continue
        if (entry / 'pyproject.toml').exists() or (entry / 'setup.py').exists():
            libs.append(str(entry.resolve()))
    return libs


def write_libraries_file(libs: List[str], output_path: str) -> None:
    """Write library paths to a file, one per line."""
    with open(output_path, 'w') as f:
        for lib in libs:
            f.write(lib + '\n')


def read_libraries_file(path: str) -> List[str]:
    """Read library paths from libraries.txt."""
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def _get_importable_name(lib_path: str) -> str:
    """Detect the actual importable Python module name for a library.
    
    The directory name may differ from the importable name (e.g., ipython -> IPython).
    """
    lib = Path(lib_path)
    name = lib.name
    
    pyproject = lib / 'pyproject.toml'
    if pyproject.exists():
        content = pyproject.read_text()
        # flit: [tool.flit.module] name = "xxx"
        flit_pat = r'\[tool\.flit\.module\]\s*\n\s*name\s*=\s*"([^"]+)"'
        m = re.search(flit_pat, content)
        if m:
            return m.group(1)
        # setuptools package-dir
        pd_pat = r'package-dir\s*=\s*\{[^}]*""\s*=\s*"([^"]+)"'
        m = re.search(pd_pat, content)
        if m:
            pkg_root = lib / m.group(1)
            if pkg_root.is_dir():
                for d in sorted(pkg_root.iterdir()):
                    if d.is_dir() and (d / '__init__.py').exists():
                        if d.name not in ('tests', 'test', 'docs', 'scripts', 'examples'):
                            if not d.name.endswith('-stubs'):
                                return d.name
    
    # Check common source locations for actual package names
    for src_root in [lib / 'src', lib / 'python', lib]:
        if src_root.is_dir():
            for d in sorted(src_root.iterdir()):
                if d.is_dir() and d.name != '__pycache__' and not d.name.startswith('.'):
                    if (d / '__init__.py').exists():
                        if d.name not in ('tests', 'test', 'docs', 'scripts', 'examples'):
                            if not d.name.endswith('-stubs'):
                                return d.name
    
    return name


def analyze_library(lib_path: str) -> Dict:
    """Analyze a library to find fuzz targets and dependencies."""
    lib = Path(lib_path)
    name = lib.name
    importable_name = _get_importable_name(lib_path)
    
    info = {
        'name': name,
        'importable_name': importable_name,
        'path': str(lib),
        'fuzz_targets': [],
        'dependencies': [],
        'build_system': 'unknown',
        'source_dir': None,
        'has_c_extension': False,
        'description': '',
    }
    
    # Read pyproject.toml
    pyproject = lib / 'pyproject.toml'
    if pyproject.exists():
        content = pyproject.read_text()
        info['pyproject_content'] = content
        
        if 'hatchling' in content:
            info['build_system'] = 'hatchling'
        elif 'flit' in content:
            info['build_system'] = 'flit'
        elif 'setuptools' in content:
            info['build_system'] = 'setuptools'
        
        # Extract dependencies
        deps = []
        in_deps = False
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('dependencies') and '=' in stripped and '[' in stripped:
                in_deps = True
                continue
            if in_deps:
                if ']' in stripped:
                    in_deps = False
                    continue
                m = re.match(r'\s*["\']([^"\']+)["\']', stripped)
                if m:
                    deps.append(m.group(1))
        info['dependencies'] = deps
        
        if 'Extension' in content or 'Programming Language :: C' in content:
            info['has_c_extension'] = True
    
    # Find source directory - try importable_name first, then dir name
    for candidate in [
        lib / 'src' / importable_name,
        lib / importable_name,
        lib / 'python' / importable_name,
        lib / 'src' / name,
        lib / name,
        lib / 'python' / name,
    ]:
        if candidate.is_dir():
            info['source_dir'] = str(candidate)
            break
    
    # Find fuzz targets
    info['fuzz_targets'] = _find_fuzz_targets(lib, importable_name, info.get('source_dir'))
    
    return info


def _find_fuzz_targets(lib_path: Path, name: str, source_dir: Optional[str]) -> List[Dict]:
    """Find good fuzz targets in a library."""
    targets = []
    if source_dir is None:
        return targets
    
    src = Path(source_dir)
    init_file = src / '__init__.py'
    if init_file.exists():
        content = init_file.read_text()
        for match in re.finditer(r'from\s+\.(\w+)\s+import\s+(.+)', content):
            module = match.group(1)
            imports = match.group(2)
            for imp in imports.split(','):
                imp = imp.strip().split(' as ')[0].strip()
                if any(kw in imp.lower() for kw in ['parse', 'load', 'decode', 'format', 'get', 'read']):
                    targets.append({
                        'function': imp,
                        'module': f"{name}.{module}",
                        'reason': 'Parser/deserializer function in public API'
                    })
    
    for py_file in src.rglob('*.py'):
        fname = py_file.stem
        if any(kw in fname.lower() for kw in ['parser', 'format', 'decode', 'serial', 'transform']):
            content = py_file.read_text()
            for match in re.finditer(r'def\s+(\w+)\s*\(', content):
                func_name = match.group(1)
                if not func_name.startswith('_'):
                    rel = py_file.relative_to(src)
                    mod = str(rel.with_suffix('')).replace('/', '.')
                    targets.append({
                        'function': func_name,
                        'module': f"{name}.{mod}",
                        'reason': f'Function in {fname} module'
                    })
    
    return targets[:10]


def generate_notes(lib_info: Dict) -> str:
    """Generate notes_for_testing.txt content from library analysis."""
    lines = []
    lines.append(f"Library: {lib_info['name']}")
    lines.append(f"Importable as: {lib_info.get('importable_name', lib_info['name'])}")
    lines.append(f"Path: {lib_info['path']}")
    lines.append(f"Build system: {lib_info['build_system']}")
    lines.append(f"Has C extension: {lib_info['has_c_extension']}")
    lines.append(f"Source directory: {lib_info.get('source_dir', 'unknown')}")
    lines.append("")
    lines.append("Dependencies:")
    for dep in lib_info.get('dependencies', []):
        lines.append(f"  - {dep}")
    lines.append("")
    lines.append("Important functions for fuzzing:")
    for i, target in enumerate(lib_info.get('fuzz_targets', []), 1):
        lines.append(f"  {i}. {target['module']}.{target['function']}")
        lines.append(f"     Reason: {target['reason']}")
    lines.append("")
    lines.append("Fuzzing strategy:")
    lines.append("  Use atheris with libFuzzer for coverage-guided fuzzing.")
    lines.append("  Target parser/deserializer entry points with string/bytes input.")
    lines.append("  Catch expected exceptions to focus on unexpected crashes.")
    return '\n'.join(lines) + '\n'


def write_notes(lib_path: str, content: str) -> None:
    """Write notes_for_testing.txt to library directory."""
    path = os.path.join(lib_path, 'notes_for_testing.txt')
    with open(path, 'w') as f:
        f.write(content)


def generate_fuzz_driver(lib_info: Dict) -> str:
    """Generate a fuzz.py driver for a library."""
    lines = _build_fuzz_body(lib_info)
    return '\n'.join(lines) + '\n'


def _build_fuzz_body(lib_info: Dict) -> List[str]:
    """Build the complete fuzz driver."""
    name = lib_info['name']
    imp_name = lib_info.get('importable_name', name)
    source_dir = lib_info.get('source_dir', '')
    
    lines = ['import sys', 'import atheris', '']
    
    # Read init content for API detection
    init_content = ''
    if source_dir:
        init_path = os.path.join(source_dir, '__init__.py')
        if os.path.exists(init_path):
            init_content = open(init_path).read()
    
    needs_selective = _needs_selective_import(imp_name, source_dir)
    
    if needs_selective:
        import_stmt, call_code, exceptions = _get_selective_target(imp_name, source_dir, lib_info)
    else:
        import_stmt, call_code, exceptions = _get_standard_target(imp_name, source_dir, init_content, lib_info)
    
    lines.append('with atheris.instrument_imports():')
    lines.append(f'    {import_stmt}')
    lines.append('')
    lines.append('@atheris.instrument_func')
    lines.append('def TestOneInput(data):')
    lines.append('    fdp = atheris.FuzzedDataProvider(data)')
    lines.append('    s = fdp.ConsumeUnicodeNoSurrogates(512)')
    lines.append('    try:')
    for cl in call_code:
        lines.append(f'        {cl}')
    lines.append(f'    except ({exceptions}):')
    lines.append('        pass')
    lines.append('    except Exception:')
    lines.append('        pass')
    lines.append('')
    lines.append('def main():')
    lines.append('    atheris.Setup(sys.argv, TestOneInput)')
    lines.append('    atheris.Fuzz()')
    lines.append('')
    lines.append('if __name__ == "__main__":')
    lines.append('    main()')
    
    return lines


def _needs_selective_import(imp_name: str, source_dir: str) -> bool:
    """Check if library needs selective import to avoid slow startup."""
    if not source_dir:
        return False
    src = Path(source_dir)
    py_count = len(list(src.rglob('*.py')))
    init_path = src / '__init__.py'
    if init_path.exists():
        content = init_path.read_text()
        if any(kw in content for kw in ['torch', 'tensorflow', 'start_ipython', 'Interactive']):
            return True
    return py_count > 50


def _get_selective_target(imp_name: str, source_dir: str, lib_info: Dict) -> Tuple[str, List[str], str]:
    """Get import and call code for libraries needing selective import."""
    src = Path(source_dir)
    
    # Look for parser/transformer/formatter submodules
    for submod in ['inputtransformer2', 'parser', 'formatter', 'transformer', 'decoder']:
        for py_file in src.rglob(f'*{submod}*.py'):
            rel = py_file.relative_to(src)
            mod_path = str(rel.with_suffix('')).replace('/', '.')
            full_mod = f"{imp_name}.{mod_path}"
            
            content = py_file.read_text()
            
            # Look for class with transform/parse method
            class_match = re.search(r'class\s+(\w*(?:Manager|Parser|Transformer)\w*)\s*[:(]', content)
            if class_match:
                cls_name = class_match.group(1)
                for method in ['transform_cell', 'transform', 'parse', 'format', 'decode']:
                    if f'def {method}' in content:
                        return (
                            f"from {full_mod} import {cls_name}",
                            [f"obj = {cls_name}()", f"obj.{method}(s)"],
                            "ValueError, TypeError, SyntaxError, IndentationError, Exception"
                        )
            
            # Look for standalone functions
            func_match = re.search(r'def\s+(parse|decode|transform|format)\w*\s*\(', content)
            if func_match:
                func_name = func_match.group(0).split('(')[0].replace('def ', '').strip()
                return (
                    f"from {full_mod} import {func_name}",
                    [f"{func_name}(s)"],
                    "ValueError, TypeError, SyntaxError, Exception"
                )
    
    # Look for env/utils modules with parsers
    for submod_name in ['env', 'utils']:
        env_file = src / f'{submod_name}.py'
        if env_file.exists():
            content = env_file.read_text()
            for match in re.finditer(r'def\s+(_?\w*(?:parse|convert|decode)\w*)\s*\(', content, re.I):
                func_name = match.group(1)
                return (
                    f"from {imp_name}.{submod_name} import {func_name}",
                    [f"{func_name}(s)"],
                    "ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError"
                )
    
    # Fallback
    return (
        f"import {imp_name}",
        [f"str({imp_name})"],
        "Exception"
    )


def _get_standard_target(imp_name: str, source_dir: str, init_content: str, lib_info: Dict) -> Tuple[str, List[str], str]:
    """Get import and call code for standard libraries."""
    
    # Code formatter with format_str (check before 'get' to avoid false match)
    if 'format_str' in init_content:
        return (
            f"import {imp_name}",
            [f"{imp_name}.format_str(s, mode={imp_name}.Mode())"],
            "ValueError, TypeError, SyntaxError, IndentationError, Exception"
        )
    
    # JSON library
    if 'json' in lib_info['name'].lower():
        if 'decode' in init_content:
            return (
                f"import {imp_name}",
                [f"{imp_name}.decode(s)"],
                "ValueError, TypeError, OverflowError, Exception"
            )
        return (
            f"import {imp_name}",
            [f"{imp_name}.loads(s)"],
            "ValueError, TypeError, OverflowError, Exception"
        )
    
    # Date/time library with .get() API
    if 'get' in init_content and ('date' in init_content.lower() or 'arrow' in init_content.lower()):
        return (
            f"import {imp_name}",
            [f"{imp_name}.get(s)"],
            "ValueError, TypeError, OverflowError, Exception"
        )
    
    # Generic: look for parse/load/decode in init
    for func in ['format_str', 'parse', 'loads', 'load', 'decode', 'get']:
        if func in init_content:
            return (
                f"import {imp_name}",
                [f"{imp_name}.{func}(s)"],
                "ValueError, TypeError, Exception"
            )
    
    # Fallback
    return (
        f"import {imp_name}",
        [f"str({imp_name})"],
        "Exception"
    )


def write_fuzz_driver(lib_path: str, content: str) -> None:
    """Write fuzz.py to library directory."""
    path = os.path.join(lib_path, 'fuzz.py')
    with open(path, 'w') as f:
        f.write(content)


def setup_venv(lib_path: str, extra_deps: Optional[List[str]] = None) -> bool:
    """Set up a Python virtual environment for a library."""
    lib = Path(lib_path)
    venv_path = lib / '.venv'
    
    # Skip if venv already exists and has python
    if (venv_path / 'bin' / 'python').exists():
        # Just ensure atheris is installed
        pip = str(venv_path / 'bin' / 'pip')
        subprocess.run([pip, 'install', '--quiet', 'atheris'], capture_output=True, text=True)
        return True
    
    result = subprocess.run(
        [sys.executable, '-m', 'venv', str(venv_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Failed to create venv for {lib.name}: {result.stderr}")
        return False
    
    pip = str(venv_path / 'bin' / 'pip')
    
    # Install atheris
    subprocess.run([pip, 'install', '--quiet', 'atheris'], capture_output=True, text=True)
    
    # Install extra dependencies
    if extra_deps:
        subprocess.run([pip, 'install', '--quiet'] + extra_deps, capture_output=True, text=True)
    
    # Install project dependencies
    deps = _extract_install_deps(lib_path)
    if deps:
        safe_deps = [d for d in deps if not _is_problematic_dep(d)]
        if safe_deps:
            subprocess.run([pip, 'install', '--quiet'] + safe_deps, capture_output=True, text=True)
    
    # Install the library itself
    result = subprocess.run(
        [pip, 'install', '--quiet', '-e', str(lib)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        result = subprocess.run(
            [pip, 'install', '--quiet', str(lib)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Warning: Could not install {lib.name}: {result.stderr[-200:]}")
    
    return True


def _extract_install_deps(lib_path: str) -> List[str]:
    """Extract install dependencies from pyproject.toml."""
    pyproject = Path(lib_path) / 'pyproject.toml'
    if not pyproject.exists():
        return []
    
    content = pyproject.read_text()
    deps = []
    in_deps = False
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('dependencies') and '=' in stripped and '[' in stripped:
            in_deps = True
            continue
        if in_deps:
            if ']' in stripped:
                in_deps = False
                continue
            m = re.match(r'\s*["\']([^"\']+)["\']', stripped)
            if m:
                deps.append(m.group(1))
    
    return deps


def _is_problematic_dep(dep: str) -> bool:
    """Check if a dependency is problematic."""
    problematic = [
        'torch', 'tensorflow', 'cuda', 'gpu', 'nvidia',
        'flashinfer', 'sgl_kernel', 'quack', 'tvm',
        'accelerate', 'modelscope',
    ]
    dep_lower = dep.lower().split('[')[0].split('>')[0].split('<')[0].split('=')[0].split(';')[0].strip()
    return any(p in dep_lower for p in problematic)


def run_fuzzer(lib_path: str, timeout: int = 10) -> Tuple[bool, str]:
    """Run the fuzzer for a library."""
    lib = Path(lib_path)
    fuzz_py = lib / 'fuzz.py'
    venv_python = lib / '.venv' / 'bin' / 'python'
    log_file = lib / 'fuzz.log'
    
    if not fuzz_py.exists():
        return False, "fuzz.py not found"
    if not venv_python.exists():
        return False, ".venv/bin/python not found"
    
    result = subprocess.run(
        [str(venv_python), str(fuzz_py), f'-max_total_time={timeout}'],
        capture_output=True,
        text=True,
        cwd=str(lib),
        timeout=timeout + 30
    )
    
    log_content = result.stderr
    with open(str(log_file), 'w') as f:
        f.write(log_content)
    
    success = 'Done' in log_content or 'DONE' in log_content
    return success, log_content


def validate_fuzz_log(log_path: str) -> Dict:
    """Validate a fuzz log file."""
    result = {
        'valid': False,
        'has_instrumentation': False,
        'has_coverage_progression': False,
        'has_completion': False,
        'final_coverage': 0,
        'total_runs': 0,
    }
    
    if not os.path.exists(log_path):
        return result
    
    content = open(log_path).read()
    
    if 'Instrumenting' in content or 'instrument' in content.lower():
        result['has_instrumentation'] = True
    
    if 'INITED' in content:
        result['has_coverage_progression'] = True
    
    done_match = re.search(r'Done\s+(\d+)\s+runs?\s+in\s+(\d+)', content)
    if done_match:
        result['has_completion'] = True
        result['total_runs'] = int(done_match.group(1))
    
    cov_matches = re.findall(r'cov:\s+(\d+)', content)
    if cov_matches:
        result['final_coverage'] = int(cov_matches[-1])
    
    result['valid'] = result['has_completion']
    return result


def run_all(base_dir: str, libraries_file: str, timeout: int = 10) -> Dict:
    """End-to-end entry point: discover, analyze, set up, and fuzz all libraries."""
    results = {}
    
    # Step 1: Discover libraries
    libs = discover_libraries(base_dir)
    write_libraries_file(libs, libraries_file)
    print(f"Discovered {len(libs)} libraries: {[Path(l).name for l in libs]}")
    
    for lib_path in libs:
        name = Path(lib_path).name
        print(f"\n{'='*60}")
        print(f"Processing: {name}")
        print(f"{'='*60}")
        
        # Step 2: Analyze library
        print(f"  Analyzing...")
        info = analyze_library(lib_path)
        print(f"  Importable name: {info['importable_name']}")
        
        # Write notes
        notes = generate_notes(info)
        write_notes(lib_path, notes)
        print(f"  Notes written")
        
        # Step 3: Generate fuzz driver
        print(f"  Generating fuzz driver...")
        driver = generate_fuzz_driver(info)
        write_fuzz_driver(lib_path, driver)
        print(f"  Fuzz driver written")
        
        # Step 4: Setup venv
        print(f"  Setting up venv...")
        venv_ok = setup_venv(lib_path)
        print(f"  Venv setup: {'OK' if venv_ok else 'FAILED'}")
        
        # Step 5: Run fuzzer
        print(f"  Running fuzzer for {timeout}s...")
        try:
            success, log = run_fuzzer(lib_path, timeout=timeout)
            print(f"  Fuzzer: {'OK' if success else 'FAILED'}")
            
            log_path = os.path.join(lib_path, 'fuzz.log')
            validation = validate_fuzz_log(log_path)
            print(f"  Coverage: {validation['final_coverage']}, Runs: {validation['total_runs']}")
            
            results[name] = {
                'venv_ok': venv_ok,
                'fuzz_ok': success,
                'validation': validation,
            }
        except Exception as e:
            print(f"  Fuzzer error: {e}")
            results[name] = {
                'venv_ok': venv_ok,
                'fuzz_ok': False,
                'error': str(e),
            }
    
    return results


def validate_all(base_dir: str, libraries_file: str) -> bool:
    """Validate that all fuzzing artifacts exist and logs are valid."""
    if not os.path.exists(libraries_file):
        print(f"FAIL: {libraries_file} not found")
        return False
    
    libs = read_libraries_file(libraries_file)
    all_ok = True
    
    for lib_path in libs:
        name = Path(lib_path).name
        for fname in ['notes_for_testing.txt', 'fuzz.py', 'fuzz.log']:
            fpath = os.path.join(lib_path, fname)
            if not os.path.exists(fpath):
                print(f"FAIL: {fpath} not found")
                all_ok = False
            elif os.path.getsize(fpath) == 0:
                print(f"FAIL: {fpath} is empty")
                all_ok = False
        
        venv_python = os.path.join(lib_path, '.venv', 'bin', 'python')
        if not os.path.exists(venv_python):
            print(f"FAIL: {venv_python} not found")
            all_ok = False
        
        log_path = os.path.join(lib_path, 'fuzz.log')
        if os.path.exists(log_path):
            validation = validate_fuzz_log(log_path)
            if not validation['valid']:
                print(f"WARN: {name} fuzz.log may not show successful completion")
    
    return all_ok
