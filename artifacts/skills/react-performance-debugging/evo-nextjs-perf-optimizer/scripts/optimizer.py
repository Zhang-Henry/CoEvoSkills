import os
import re
import subprocess
import json


def find_source_files(app_dir):
    """Find all TypeScript/TSX source files in the app."""
    src_dir = os.path.join(app_dir, 'src')
    files = []
    for root, dirs, filenames in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != 'node_modules' and d != '.next']
        for f in filenames:
            if f.endswith(('.ts', '.tsx', '.js', '.jsx')):
                files.append(os.path.join(root, f))
    return files


def detect_sequential_fetches(content):
    """Detect sequential await patterns for independent fetches.
    Returns list of (line_numbers, fetch_names) tuples."""
    lines = content.split('\n')
    sequential_awaits = []
    current_group = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match patterns like: const x = await fetchSomething();
        match = re.match(r'(?:const|let|var)\s+\w+\s*=\s*await\s+(\w+)\(', stripped)
        if match:
            current_group.append((i + 1, match.group(1)))
        else:
            if len(current_group) >= 2:
                sequential_awaits.append(current_group)
            current_group = []
    
    if len(current_group) >= 2:
        sequential_awaits.append(current_group)
    
    return sequential_awaits


def detect_barrel_imports(content):
    """Detect barrel imports from libraries like lodash."""
    barrel_imports = []
    for match in re.finditer(r"import\s*\{([^}]+)\}\s*from\s*['\"]lodash['\"]", content):
        names = [n.strip() for n in match.group(1).split(',')]
        barrel_imports.append(('lodash', names, match.start()))
    return barrel_imports


def detect_missing_memo(content, filename):
    """Detect components that could benefit from React.memo."""
    issues = []
    # Check if it's a component file with export function
    if re.search(r'export\s+function\s+\w+', content):
        if 'React.memo' not in content and 'memo(' not in content:
            if 'onAddToCart' in content or 'onClick' in content:
                issues.append(f'{filename}: Component not wrapped in React.memo')
    return issues


def detect_missing_usecallback(content, filename):
    """Detect inline function handlers that should use useCallback."""
    issues = []
    if 'useState' in content:
        # Check for handler functions defined without useCallback
        handlers = re.findall(r'const\s+(handle\w+)\s*=\s*\(', content)
        if handlers and 'useCallback' not in content:
            issues.append(f'{filename}: Handlers {handlers} not using useCallback')
    return issues


def detect_missing_usememo(content, filename):
    """Detect expensive computations that should use useMemo."""
    issues = []
    if 'useState' in content:
        # Check for filter/sort/map chains without useMemo
        if re.search(r'\w+\s*\.filter\(.*\.sort\(', content, re.DOTALL):
            if 'useMemo' not in content:
                issues.append(f'{filename}: Filter/sort chain without useMemo')
        # Check for linear search in render (reviews.filter inside render)
        if re.search(r'reviews\.filter\(', content):
            if 'useMemo' not in content:
                issues.append(f'{filename}: Linear search per item without useMemo lookup map')
    return issues


def detect_awaited_analytics(content):
    """Detect awaited analytics/logging calls that should be fire-and-forget."""
    issues = []
    for match in re.finditer(r'await\s+(log\w+|track\w+|analytics\w*)', content, re.IGNORECASE):
        issues.append(f'Awaited non-critical call: {match.group(1)}')
    return issues


def detect_missing_dynamic_import(content, filename):
    """Detect heavy library imports that should be dynamically loaded."""
    issues = []
    heavy_libs = ['mathjs', 'chart.js', 'd3', 'three']
    for lib in heavy_libs:
        if f"from '{lib}'" in content or f'from "{lib}"' in content:
            if 'dynamic(' not in content and "dynamic import" not in content:
                issues.append(f'{filename}: Heavy library {lib} imported statically')
    return issues


def analyze_app(app_dir):
    """Run all detectors on the app and return a report."""
    files = find_source_files(app_dir)
    report = {
        'sequential_fetches': [],
        'barrel_imports': [],
        'missing_memo': [],
        'missing_usecallback': [],
        'missing_usememo': [],
        'awaited_analytics': [],
        'missing_dynamic_import': [],
    }
    
    for filepath in files:
        with open(filepath, 'r') as f:
            content = f.read()
        
        rel_path = os.path.relpath(filepath, app_dir)
        
        seq = detect_sequential_fetches(content)
        if seq:
            report['sequential_fetches'].append((rel_path, seq))
        
        barrel = detect_barrel_imports(content)
        if barrel:
            report['barrel_imports'].append((rel_path, barrel))
        
        report['missing_memo'].extend(detect_missing_memo(content, rel_path))
        report['missing_usecallback'].extend(detect_missing_usecallback(content, rel_path))
        report['missing_usememo'].extend(detect_missing_usememo(content, rel_path))
        report['awaited_analytics'].extend(detect_awaited_analytics(content))
        report['missing_dynamic_import'].extend(detect_missing_dynamic_import(content, rel_path))
    
    return report


def parallelize_fetches(content):
    """Transform sequential independent awaits into Promise.all."""
    lines = content.split('\n')
    result_lines = []
    i = 0
    
    while i < len(lines):
        stripped = lines[i].strip()
        match = re.match(r'(\s*)(?:const|let|var)\s+(\w+)\s*=\s*await\s+(\w+\([^)]*\));', stripped)
        
        if match:
            group = [(lines[i], match)]
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                next_match = re.match(r'(\s*)(?:const|let|var)\s+(\w+)\s*=\s*await\s+(\w+\([^)]*\));', next_stripped)
                if next_match:
                    group.append((lines[j], next_match))
                    j += 1
                elif next_stripped == '' or next_stripped.startswith('//'):
                    j += 1
                else:
                    break
            
            if len(group) >= 2:
                indent = re.match(r'(\s*)', lines[i]).group(1)
                var_names = [m.group(2) for _, m in group]
                func_calls = [m.group(3) for _, m in group]
                
                result_lines.append(f'{indent}const [{', '.join(var_names)}] = await Promise.all([')
                for k, call in enumerate(func_calls):
                    comma = ',' if k < len(func_calls) - 1 else ''
                    result_lines.append(f'{indent}  {call}{comma}')
                result_lines.append(f'{indent}]);')
                i = j
                continue
        
        result_lines.append(lines[i])
        i += 1
    
    return '\n'.join(result_lines)


def convert_barrel_to_direct_imports(content):
    """Convert lodash barrel imports to direct imports."""
    def replace_barrel(match):
        names = [n.strip() for n in match.group(1).split(',')]
        imports = []
        for name in names:
            if name:  # skip empty strings
                imports.append(f"import {name} from 'lodash/{name}';")
        return '\n'.join(imports)
    
    return re.sub(r"import\s*\{([^}]+)\}\s*from\s*['\"]lodash['\"]", replace_barrel, content)


def run_optimization(app_dir):
    """Run the full optimization pipeline on the app."""
    print(f"Analyzing {app_dir}...")
    report = analyze_app(app_dir)
    
    issues_found = sum(len(v) if isinstance(v, list) else 0 for v in report.values())
    print(f"Found {issues_found} potential issues")
    
    for category, items in report.items():
        if items:
            print(f"\n{category}:")
            for item in items:
                print(f"  - {item}")
    
    return report


def validate_optimization(app_dir):
    """Validate that optimizations are properly applied."""
    files = find_source_files(app_dir)
    errors = []
    
    for filepath in files:
        with open(filepath, 'r') as f:
            content = f.read()
        
        rel_path = os.path.relpath(filepath, app_dir)
        
        # Check data-testid attributes are preserved
        if 'data-testid' in content:
            print(f"  OK: {rel_path} preserves data-testid attributes")
        
        # Check performance.mark is preserved in ProductCard
        if 'ProductCard' in rel_path:
            if 'performance.mark' not in content:
                errors.append(f"{rel_path}: Missing performance.mark()")
            else:
                print(f"  OK: {rel_path} preserves performance.mark()")
            
            if 'React.memo' not in content and 'memo(' not in content:
                errors.append(f"{rel_path}: ProductCard not wrapped in React.memo")
            else:
                print(f"  OK: {rel_path} uses React.memo")
    
    # Check for sequential fetches remaining
    for filepath in files:
        with open(filepath, 'r') as f:
            content = f.read()
        rel_path = os.path.relpath(filepath, app_dir)
        seq = detect_sequential_fetches(content)
        if seq:
            errors.append(f"{rel_path}: Still has sequential fetches")
    
    # Verify build succeeds
    print("\nRunning build verification...")
    result = subprocess.run(
        ['npm', 'run', 'build'],
        cwd=app_dir,
        capture_output=True,
        text=True,
        timeout=120
    )
    if result.returncode != 0:
        errors.append(f"Build failed: {result.stderr[-500:]}")
    else:
        print("  OK: Build succeeded")
    
    if errors:
        print(f"\nValidation FAILED with {len(errors)} errors:")
        for e in errors:
            print(f"  ERROR: {e}")
        return False
    else:
        print("\nValidation PASSED")
        return True
