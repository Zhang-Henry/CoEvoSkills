import os
import subprocess
import glob


def discover_repo(base_path):
    """Discover the repository path under the base failed build directory.
    Returns the path to the actual repo (e.g., /home/github/build/failed/Org/repo)."""
    for org_dir in os.listdir(base_path):
        org_path = os.path.join(base_path, org_dir)
        if os.path.isdir(org_path) and org_dir not in ('cacher',):
            for repo_dir in os.listdir(org_path):
                repo_path = os.path.join(org_path, repo_dir)
                if os.path.isdir(repo_path) and os.path.isdir(os.path.join(repo_path, '.git')):
                    return repo_path
    return None


def run_tox_env(repo_path, env_name, timeout=120):
    """Run a specific tox environment and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ['tox', '-e', env_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, '', 'Timeout'
    except Exception as e:
        return -1, '', str(e)


def get_tox_envlist(repo_path):
    """Parse tox.ini to get the envlist."""
    tox_ini = os.path.join(repo_path, 'tox.ini')
    if not os.path.exists(tox_ini):
        return []
    envs = []
    with open(tox_ini) as f:
        in_tox_section = False
        for line in f:
            line = line.strip()
            if line == '[tox]':
                in_tox_section = True
                continue
            if line.startswith('[') and in_tox_section:
                break
            if in_tox_section and line.startswith('envlist'):
                _, _, val = line.partition('=')
                envs = [e.strip() for e in val.split(',') if e.strip()]
    return envs


def get_available_pythons():
    """Discover which Python versions are available on the system."""
    available = {}
    for minor in range(7, 13):
        name = f'python3.{minor}'
        try:
            result = subprocess.run([name, '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                available[f'py3{minor}'] = name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return available


def classify_error(stdout, stderr):
    """Classify a build error from tox output into categories."""
    combined = stdout + stderr
    categories = []
    if 'SyntaxError' in combined:
        categories.append('syntax_error')
    if 'ImportError' in combined or 'ModuleNotFoundError' in combined:
        categories.append('import_error')
    if 'TypeError' in combined:
        categories.append('type_error')
    if 'AttributeError' in combined:
        categories.append('attribute_error')
    if 'AssertionError' in combined or 'AssertionError' in combined:
        categories.append('assertion_error')
    if not categories:
        categories.append('unknown')
    return categories


def analyze_build_failure(repo_path):
    """Analyze a build failure by running tox environments and collecting errors."""
    envs = get_tox_envlist(repo_path)
    available = get_available_pythons()
    results = {}
    for env in envs:
        if env in available or env in ('py310',):  # py310 maps to python3.10
            rc, stdout, stderr = run_tox_env(repo_path, env)
            results[env] = {
                'returncode': rc,
                'stdout': stdout,
                'stderr': stderr,
                'categories': classify_error(stdout, stderr) if rc != 0 else ['pass']
            }
    return {
        'repo_path': repo_path,
        'envs_tested': list(results.keys()),
        'results': results,
        'fixes': []  # To be populated by the caller after analysis
    }


def write_analysis(analysis_text, output_path):
    """Write analysis text to the output file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(analysis_text)


def generate_patch(repo_path, filepath, old_line, new_line):
    """Generate a patch by making a change and capturing git diff.
    
    Args:
        repo_path: Path to the git repository
        filepath: Relative path to the file within the repo
        old_line: The exact line content to replace
        new_line: The replacement line content
    
    Returns:
        str: The unified diff content
    """
    full_path = os.path.join(repo_path, filepath)
    with open(full_path) as f:
        content = f.read()
    
    if old_line not in content:
        raise ValueError(f"Could not find line to replace in {filepath}: {old_line!r}")
    
    new_content = content.replace(old_line, new_line, 1)
    with open(full_path, 'w') as f:
        f.write(new_content)
    
    result = subprocess.run(
        ['git', 'diff', '--', filepath],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return result.stdout


def apply_patches(repo_path):
    """Apply all patch_*.diff files in the repo directory."""
    patch_files = sorted(glob.glob(os.path.join(repo_path, 'patch_*.diff')))
    results = []
    for pf in patch_files:
        # Check if already applied by trying reverse
        check = subprocess.run(
            ['git', 'apply', '--check', '--reverse', pf],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if check.returncode == 0:
            results.append((pf, 'already_applied'))
            continue
        
        result = subprocess.run(
            ['git', 'apply', pf],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            results.append((pf, 'applied'))
        else:
            results.append((pf, f'failed: {result.stderr}'))
    return results


def validate_outputs(repo_path, analysis_path):
    """Validate that all required output artifacts exist."""
    errors = []
    if not os.path.exists(analysis_path):
        errors.append(f'Missing analysis file: {analysis_path}')
    
    patch_files = glob.glob(os.path.join(repo_path, 'patch_*.diff'))
    if not patch_files:
        errors.append(f'No patch files found in {repo_path}')
    
    for pf in patch_files:
        with open(pf) as f:
            content = f.read()
        if not content.strip():
            errors.append(f'Empty patch file: {pf}')
        if '---' not in content or '+++' not in content:
            errors.append(f'Malformed patch file (missing headers): {pf}')
        if '@@' not in content:
            errors.append(f'Malformed patch file (missing hunk headers): {pf}')
    
    # Verify changes are applied to source
    result = subprocess.run(
        ['git', 'diff', '--stat'],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if not result.stdout.strip():
        errors.append('No changes detected in repository - patches may not be applied')
    
    if errors:
        raise ValueError('Validation errors:\n' + '\n'.join(errors))
    
    return True
