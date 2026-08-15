import os
import glob
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def discover_repo(failed_dir: str) -> Tuple[str, str, str]:
    """Discover the repository path, name, and id under the failed directory.
    
    Args:
        failed_dir: Path to /home/github/build/failed
    Returns:
        Tuple of (repo_path, org_name, repo_name)
    """
    for org in os.listdir(failed_dir):
        org_path = os.path.join(failed_dir, org)
        if not os.path.isdir(org_path):
            continue
        for repo in os.listdir(org_path):
            repo_path = os.path.join(org_path, repo)
            if os.path.isdir(repo_path) and os.path.isdir(os.path.join(repo_path, '.git')):
                return repo_path, org, repo
    raise FileNotFoundError(f"No git repository found under {failed_dir}")


def analyze_build_logs(build_dir: str) -> Dict:
    """Analyze CI build log files to identify failure patterns.
    
    Args:
        build_dir: Path to /home/github/build
    Returns:
        Dict with 'summary', 'errors', 'failing_tests', 'failing_envs'
    """
    result = {
        'summary': '',
        'errors': [],
        'failing_tests': [],
        'failing_envs': [],
        'log_files': []
    }
    
    log_files = glob.glob(os.path.join(build_dir, '*.log'))
    result['log_files'] = log_files
    
    for log_file in log_files:
        with open(log_file, 'r', errors='replace') as f:
            content = f.read()
        
        # Find FAIL lines
        for line in content.split('\n'):
            if 'FAIL' in line and ('✖' in line or 'code 1' in line):
                env_match = re.search(r'(py\d+):', line)
                if env_match:
                    result['failing_envs'].append(env_match.group(1))
            
            # Find assertion errors and test failures
            if 'FAILED' in line and '::' in line:
                result['failing_tests'].append(line.strip())
            
            # Find error lines with tracebacks
            if 'Error' in line and ('assert' in line.lower() or 'error' in line.lower()):
                result['errors'].append(line.strip())
    
    if result['failing_tests']:
        result['summary'] = f"Tests failing: {', '.join(result['failing_tests'][:5])}"
    elif result['errors']:
        result['summary'] = f"Errors found: {result['errors'][0][:200]}"
    else:
        result['summary'] = 'No specific failure pattern identified from logs'
    
    return result


def find_source_files(repo_path: str, extensions: List[str] = None) -> List[str]:
    """Find all Python source files in the repository.
    
    Args:
        repo_path: Path to the repository root
        extensions: File extensions to search for (default: ['.py'])
    Returns:
        List of file paths
    """
    if extensions is None:
        extensions = ['.py']
    
    files = []
    for ext in extensions:
        for f in Path(repo_path).rglob(f'*{ext}'):
            if '.git' not in str(f) and '__pycache__' not in str(f) and '.tox' not in str(f):
                files.append(str(f))
    return sorted(files)


def check_version_compat_issues(source_files: List[str]) -> List[Dict]:
    """Check source files for Python version compatibility issues.
    
    Looks for constructs that are only available in newer Python versions:
    - list[Type] (3.9+)
    - dict[K,V] (3.9+)
    - match statements (3.10+)
    - walrus operator (3.8+)
    
    Args:
        source_files: List of Python file paths to check
    Returns:
        List of dicts with 'file', 'line', 'issue', 'suggestion'
    """
    issues = []
    
    # Pattern for lowercase generic types used as type hints
    # Matches: list[, dict[, tuple[, set[, type[ in type annotation context
    lowercase_generic_pattern = re.compile(
        r'(?::\s*|->\s*)(?:list|dict|tuple|set|type)\['
    )
    
    for filepath in source_files:
        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            continue
        
        for i, line in enumerate(lines, 1):
            # Check for lowercase generic types
            if lowercase_generic_pattern.search(line):
                issues.append({
                    'file': filepath,
                    'line': i,
                    'issue': f'Lowercase generic type hint (Python 3.9+ only): {line.strip()}',
                    'suggestion': 'Use typing.List, typing.Dict, etc. for Python 3.7/3.8 compatibility'
                })
    
    return issues


def write_analysis(output_path: str, logs: Dict, issues: List[Dict],
                   additional_notes: str = '') -> None:
    """Write the build failure analysis to a file.
    
    Args:
        output_path: Path to write the analysis file
        logs: Result from analyze_build_logs()
        issues: Result from check_version_compat_issues()
        additional_notes: Additional analysis notes
    """
    with open(output_path, 'w') as f:
        f.write('## Build Failure Analysis\n\n')
        f.write(f'### Summary\n{logs["summary"]}\n\n')
        
        if logs['failing_envs']:
            f.write(f'### Failing Environments\n')
            for env in logs['failing_envs']:
                f.write(f'- {env}\n')
            f.write('\n')
        
        if logs['failing_tests']:
            f.write(f'### Failing Tests\n')
            for test in logs['failing_tests']:
                f.write(f'- {test}\n')
            f.write('\n')
        
        if issues:
            f.write('### Version Compatibility Issues\n')
            for issue in issues:
                f.write(f'- {issue["file"]}:{issue["line"]}: {issue["issue"]}\n')
                f.write(f'  Suggestion: {issue["suggestion"]}\n')
            f.write('\n')
        
        if additional_notes:
            f.write(f'### Additional Notes\n{additional_notes}\n')


def create_patch_from_git_diff(repo_path: str, patch_number: int,
                                specific_files: List[str] = None) -> str:
    """Create a patch file from git diff.
    
    Args:
        repo_path: Path to the repository root
        patch_number: Patch number (for naming patch_N.diff)
        specific_files: Optional list of specific files to diff
    Returns:
        Path to the created patch file
    """
    patch_path = os.path.join(repo_path, f'patch_{patch_number}.diff')
    
    cmd = ['git', 'diff']
    if specific_files:
        cmd.append('--')
        cmd.extend(specific_files)
    
    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
    
    with open(patch_path, 'w') as f:
        f.write(result.stdout)
    
    return patch_path


def verify_patch_applies(repo_path: str, patch_number: int) -> bool:
    """Verify a patch file can be applied cleanly.
    
    Args:
        repo_path: Path to the repository root
        patch_number: Patch number
    Returns:
        True if patch applies cleanly
    """
    patch_path = os.path.join(repo_path, f'patch_{patch_number}.diff')
    
    # First revert changes
    subprocess.run(['git', 'checkout', '.'], cwd=repo_path, capture_output=True)
    
    # Try to apply
    result = subprocess.run(
        ['git', 'apply', '--check', patch_path],
        cwd=repo_path, capture_output=True, text=True
    )
    
    if result.returncode == 0:
        # Actually apply it
        subprocess.run(['git', 'apply', patch_path], cwd=repo_path, capture_output=True)
        return True
    else:
        print(f"Patch verification failed: {result.stderr}")
        return False


def run_tests(repo_path: str, test_cmd: str = None) -> Tuple[bool, str]:
    """Run the test suite and return results.
    
    Args:
        repo_path: Path to the repository root
        test_cmd: Custom test command (default: python3 -m pytest tests/ -v)
    Returns:
        Tuple of (success, output)
    """
    if test_cmd is None:
        test_cmd = 'python3 -m pytest tests/ -v'
    
    result = subprocess.run(
        test_cmd.split(),
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120
    )
    
    output = result.stdout + result.stderr
    success = result.returncode == 0
    
    return success, output
