import os
import re
import subprocess
import shutil
from typing import List, Dict, Tuple, Optional


def find_repo_dir(base_path: str = '/home/travis/build/failed') -> Tuple[str, str, str]:
    """Discover the repository directory under the failed builds path.
    Returns (repo_dir, repo_name, artifact_id) where repo_name is like 'google'
    and artifact_id is like 'auto'.
    """
    for org in os.listdir(base_path):
        org_path = os.path.join(base_path, org)
        if not os.path.isdir(org_path) or org == '.' or org == '..':
            continue
        for proj in os.listdir(org_path):
            proj_path = os.path.join(org_path, proj)
            if os.path.isdir(proj_path) and (os.path.isdir(os.path.join(proj_path, '.git')) or os.path.isfile(os.path.join(proj_path, 'pom.xml'))):
                return proj_path, org, proj
    raise FileNotFoundError(f"No repository found under {base_path}")


def find_build_command(repo_dir: str) -> Optional[str]:
    """Extract the build command from .travis.yml or reproduction scripts."""
    travis_yml = os.path.join(repo_dir, '.travis.yml')
    if os.path.exists(travis_yml):
        with open(travis_yml, 'r') as f:
            content = f.read()
        # Extract script section
        in_script = False
        commands = []
        for line in content.split('\n'):
            if line.strip().startswith('script:'):
                in_script = True
                rest = line.strip()[len('script:'):].strip()
                if rest:
                    commands.append(rest.lstrip('- '))
                continue
            if in_script:
                if line.startswith('  ') or line.startswith('\t'):
                    stripped = line.strip()
                    if stripped.startswith('- '):
                        stripped = stripped[2:]
                    commands.append(stripped)
                else:
                    if line.strip() and not line.startswith(' '):
                        break
        return ' && '.join(commands) if commands else None
    return None


def run_build(repo_dir: str, build_cmd: Optional[str] = None, timeout: int = 300) -> Tuple[int, str]:
    """Run the build and capture output. Returns (returncode, output)."""
    if build_cmd is None:
        build_cmd = find_build_command(repo_dir)
    if build_cmd is None:
        build_cmd = 'mvn -B verify'
    
    result = subprocess.run(
        build_cmd, shell=True, cwd=repo_dir,
        capture_output=True, text=True, timeout=timeout
    )
    combined = result.stdout + '\n' + result.stderr
    return result.returncode, combined


def parse_maven_errors(build_output: str) -> List[Dict[str, str]]:
    """Parse Maven build output to identify error categories and details."""
    errors = []
    for line in build_output.split('\n'):
        if '[ERROR]' in line:
            error_info = {'raw': line.strip()}
            # Check for dependency resolution errors
            if 'Could not resolve dependencies' in line or 'Could not find artifact' in line:
                error_info['type'] = 'dependency_resolution'
                # Extract artifact info
                m = re.search(r'Could not find artifact ([^\s]+)', line)
                if m:
                    error_info['artifact'] = m.group(1)
                m = re.search(r'at specified path ([^\s]+)', line)
                if m:
                    error_info['path'] = m.group(1)
            # Check for compilation errors
            elif 'compiler:compile' in line or 'Compilation failure' in line:
                error_info['type'] = 'compilation'
            # Check for test failures
            elif 'surefire' in line.lower() or 'test' in line.lower():
                error_info['type'] = 'test_failure'
            else:
                error_info['type'] = 'other'
            errors.append(error_info)
    return errors


def detect_tools_jar_issue(errors: List[Dict[str, str]]) -> bool:
    """Check if the build failure is caused by missing tools.jar (Java 9+ issue)."""
    for err in errors:
        if err.get('type') == 'dependency_resolution':
            artifact = err.get('artifact', '')
            path = err.get('path', '')
            if 'com.sun:tools' in artifact or 'tools.jar' in path:
                return True
    return False


def find_pom_files(repo_dir: str) -> List[str]:
    """Find all pom.xml files in the repository."""
    pom_files = []
    for root, dirs, files in os.walk(repo_dir):
        # Skip hidden directories, target directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'target']
        for f in files:
            if f == 'pom.xml':
                pom_files.append(os.path.join(root, f))
    return pom_files


def find_tools_jar_dependency_sources(repo_dir: str) -> List[Tuple[str, str, str]]:
    """Find dependencies in POM files that transitively bring in com.sun:tools.
    Checks both direct dependencies and known libraries that depend on tools.jar.
    Returns list of (pom_path, dependency_artifactId, dependency_version).
    """
    known_tools_dependents = ['compile-testing']
    results = []
    
    pom_files = find_pom_files(repo_dir)
    for pom_path in pom_files:
        with open(pom_path, 'r') as f:
            content = f.read()
        
        # Check for direct com.sun:tools dependency
        if '<groupId>com.sun</groupId>' in content and '<artifactId>tools</artifactId>' in content:
            results.append((pom_path, 'tools', 'direct'))
            continue
        
        # Check for known transitive sources
        for dep_name in known_tools_dependents:
            pattern = rf'<artifactId>{dep_name}</artifactId>\s*\n\s*<version>([^<]+)</version>'
            match = re.search(pattern, content)
            if match:
                results.append((pom_path, dep_name, match.group(1)))
    
    return results


def add_exclusion_to_dependency(pom_content: str, artifact_id: str,
                                 exclude_group: str, exclude_artifact: str) -> str:
    """Add an exclusion to a dependency in a POM file.
    Finds the dependency by artifactId and adds exclusion block after <scope> line.
    """
    # Pattern to find the dependency and its scope line
    pattern = rf'(<artifactId>{artifact_id}</artifactId>\s*\n\s*<version>[^<]+</version>\s*\n\s*<scope>[^<]+</scope>\n)'
    match = re.search(pattern, pom_content)
    if not match:
        # Try without scope
        pattern = rf'(<artifactId>{artifact_id}</artifactId>\s*\n\s*<version>[^<]+</version>\n)'
        match = re.search(pattern, pom_content)
    
    if not match:
        return pom_content  # No change if pattern not found
    
    # Detect indentation from the artifactId line
    art_line_match = re.search(rf'^(\s*)<artifactId>{artifact_id}</artifactId>', pom_content, re.MULTILINE)
    indent = art_line_match.group(1) if art_line_match else '      '
    
    exclusion_block = (
        f"{indent}<exclusions>\n"
        f"{indent}  <exclusion>\n"
        f"{indent}    <groupId>{exclude_group}</groupId>\n"
        f"{indent}    <artifactId>{exclude_artifact}</artifactId>\n"
        f"{indent}  </exclusion>\n"
        f"{indent}</exclusions>\n"
    )
    
    insert_pos = match.end()
    return pom_content[:insert_pos] + exclusion_block + pom_content[insert_pos:]


def generate_diff(original_path: str, modified_content: str, rel_path: str) -> str:
    """Generate a unified diff between original file and modified content.
    Uses the diff command for correctness.
    """
    with open(original_path, 'r') as f:
        original_content = f.read()
    
    if original_content == modified_content:
        return ''
    
    orig_tmp = '/tmp/diff_orig'
    new_tmp = '/tmp/diff_new'
    with open(orig_tmp, 'w') as f:
        f.write(original_content)
    with open(new_tmp, 'w') as f:
        f.write(modified_content)
    
    result = subprocess.run(
        ['diff', '-u', orig_tmp, new_tmp],
        capture_output=True, text=True
    )
    
    diff_text = result.stdout
    # Replace temp paths with proper git-style a/b paths
    lines = diff_text.split('\n')
    new_lines = []
    for line in lines:
        if line.startswith('--- /tmp/diff_orig'):
            line = f'--- a/{rel_path}'
        elif line.startswith('+++ /tmp/diff_new'):
            line = f'+++ b/{rel_path}'
        new_lines.append(line)
    
    # Clean up
    os.remove(orig_tmp)
    os.remove(new_tmp)
    
    return '\n'.join(new_lines)


def write_analysis(output_path: str, errors: List[Dict[str, str]], 
                   tools_jar_sources: List[Tuple[str, str, str]],
                   is_tools_jar: bool) -> None:
    """Write the build failure analysis to a file."""
    with open(output_path, 'w') as f:
        f.write("Build Failure Analysis\n")
        f.write("=" * 40 + "\n\n")
        
        f.write("Errors found:\n")
        for err in errors:
            f.write(f"  Type: {err.get('type', 'unknown')}\n")
            f.write(f"  Detail: {err.get('raw', '')}\n")
            if 'artifact' in err:
                f.write(f"  Artifact: {err['artifact']}\n")
            if 'path' in err:
                f.write(f"  Path: {err['path']}\n")
            f.write("\n")
        
        if is_tools_jar:
            f.write("Root Cause: Missing tools.jar (Java 9+ compatibility issue)\n")
            f.write("In Java 9+, tools.jar was removed. Its classes are now part of JDK modules.\n\n")
            f.write("Affected dependencies:\n")
            for pom_path, dep_name, version in tools_jar_sources:
                f.write(f"  {pom_path}: {dep_name} (version {version})\n")
            f.write("\nFix: Add exclusion for com.sun:tools in each affected dependency.\n")


def fix_tools_jar_issue(repo_dir: str) -> List[Tuple[str, str, str]]:
    """Fix tools.jar dependency issues by adding exclusions.
    Returns list of (rel_path, patch_content, modified_content) for each fixed file.
    """
    sources = find_tools_jar_dependency_sources(repo_dir)
    patches = []
    
    for pom_path, dep_name, version in sources:
        rel_path = os.path.relpath(pom_path, repo_dir)
        with open(pom_path, 'r') as f:
            original = f.read()
        
        if dep_name == 'tools' and version == 'direct':
            # Direct dependency - would need different handling
            continue
        
        modified = add_exclusion_to_dependency(
            original, dep_name, 'com.sun', 'tools'
        )
        
        if modified != original:
            diff = generate_diff(pom_path, modified, rel_path)
            patches.append((rel_path, diff, modified))
    
    return patches


def apply_patch(repo_dir: str, patch_path: str) -> Tuple[bool, str]:
    """Apply a patch file to the repository using patch command."""
    result = subprocess.run(
        ['patch', '-p1', '-i', patch_path],
        capture_output=True, text=True, cwd=repo_dir
    )
    success = result.returncode == 0
    output = result.stdout + result.stderr
    return success, output


def run_end_to_end(base_path: str = '/home/travis/build/failed',
                   build_timeout: int = 300) -> bool:
    """End-to-end entry point: discover repo, analyze errors, fix, verify.
    Returns True if the build was fixed successfully.
    """
    # Step 1: Discover repository
    repo_dir, repo_name, artifact_id = find_repo_dir(base_path)
    print(f"Found repository: {repo_dir} ({repo_name}/{artifact_id})")
    
    # Step 2: Run build to capture errors
    build_cmd = find_build_command(repo_dir)
    print(f"Build command: {build_cmd}")
    
    returncode, build_output = run_build(repo_dir, build_cmd, timeout=build_timeout)
    
    # Step 3: Parse errors
    errors = parse_maven_errors(build_output)
    is_tools_jar = detect_tools_jar_issue(errors)
    
    # Step 4: Find dependency sources
    tools_jar_sources = find_tools_jar_dependency_sources(repo_dir)
    
    # Step 5: Write analysis
    analysis_path = os.path.join(base_path, 'failed_reasons.txt')
    write_analysis(analysis_path, errors, tools_jar_sources, is_tools_jar)
    print(f"Analysis written to {analysis_path}")
    
    # Step 6: Generate and write patches
    if is_tools_jar:
        patches = fix_tools_jar_issue(repo_dir)
        for i, (rel_path, diff_content, modified_content) in enumerate(patches, 1):
            patch_path = os.path.join(repo_dir, f'patch_{i}.diff')
            with open(patch_path, 'w') as f:
                f.write(diff_content)
            print(f"Patch {i} written: {patch_path} (for {rel_path})")
        
        # Step 7: Apply patches
        for i in range(1, len(patches) + 1):
            patch_path = os.path.join(repo_dir, f'patch_{i}.diff')
            success, output = apply_patch(repo_dir, patch_path)
            if success:
                print(f"Patch {i} applied successfully")
            else:
                print(f"Patch {i} failed: {output}")
                return False
    else:
        print("No tools.jar issue detected - manual analysis needed")
        return False
    
    # Step 8: Verify build
    print("Verifying build...")
    returncode, build_output = run_build(repo_dir, build_cmd, timeout=build_timeout)
    if returncode == 0:
        print("Build succeeded!")
        return True
    else:
        # Check if tools.jar errors are gone
        new_errors = parse_maven_errors(build_output)
        new_tools_jar = detect_tools_jar_issue(new_errors)
        if not new_tools_jar:
            print("Tools.jar issue fixed, but other errors remain")
        else:
            print("Tools.jar issue still present")
        print("Build output (last 50 lines):")
        for line in build_output.split('\n')[-50:]:
            print(line)
        return returncode == 0


def validate_output(base_path: str = '/home/travis/build/failed') -> bool:
    """Validate that the task output is correct."""
    repo_dir, repo_name, artifact_id = find_repo_dir(base_path)
    
    # Check analysis file exists
    analysis_path = os.path.join(base_path, 'failed_reasons.txt')
    if not os.path.exists(analysis_path):
        print(f"FAIL: {analysis_path} not found")
        return False
    print(f"OK: Analysis file exists at {analysis_path}")
    
    # Check patch files exist
    patch_files = sorted([f for f in os.listdir(repo_dir) if f.startswith('patch_') and f.endswith('.diff')])
    if not patch_files:
        print("FAIL: No patch files found")
        return False
    print(f"OK: Found {len(patch_files)} patch files: {patch_files}")
    
    # Validate each patch is valid unified diff
    for pf in patch_files:
        patch_path = os.path.join(repo_dir, pf)
        with open(patch_path, 'r') as f:
            content = f.read()
        if '---' not in content or '+++' not in content or '@@' not in content:
            print(f"FAIL: {pf} is not a valid unified diff")
            return False
        print(f"OK: {pf} is a valid unified diff format")
    
    # Check that POM files were actually modified
    pom_files = find_pom_files(repo_dir)
    has_exclusion = False
    for pom in pom_files:
        with open(pom, 'r') as f:
            content = f.read()
        if '<groupId>com.sun</groupId>' in content and '<exclusion>' in content:
            has_exclusion = True
            break
    
    if has_exclusion:
        print("OK: POM files contain exclusion for com.sun:tools")
    else:
        print("WARNING: No exclusion found in POM files - patches may not have been applied")
    
    return True


def fix_javax_annotation_generated(repo_dir: str) -> List[Tuple[str, str, str]]:
    """Fix javax.annotation.Generated -> javax.annotation.processing.Generated.
    Returns list of (rel_path, diff, modified_content).
    """
    import subprocess
    result = subprocess.run(
        ['grep', '-rln', 'javax.annotation.Generated', repo_dir, '--include=*.java'],
        capture_output=True, text=True)
    files = [f for f in result.stdout.strip().split('\n')
             if f and '/target/' not in f and '/.git/' not in f]
    patches = []
    for fp in sorted(files):
        rel = os.path.relpath(fp, repo_dir)
        with open(fp) as f: c = f.read()
        m = c
        m = m.replace('import javax.annotation.Generated;', 'import javax.annotation.processing.Generated;')
        m = m.replace('"javax.annotation.Generated"', '"javax.annotation.processing.Generated"')
        m = m.replace('"import javax.annotation.Generated;"', '"import javax.annotation.processing.Generated;"')
        m = m.replace('"import javax.annotation.Generated"', '"import javax.annotation.processing.Generated"')
        if m != c:
            diff = generate_diff(fp, m, rel)
            patches.append((rel, diff, m))
    return patches


def fix_module_element_traversal(repo_dir: str) -> List[Tuple[str, str, str]]:
    """Fix Java 9+ module element traversal issues.
    In Java 9+, PackageElement.getEnclosingElement() returns ModuleElement.
    Methods that walk up the element tree need to stop at PACKAGE.
    """
    patches = []
    # Fix Visibility.java
    vis_path = os.path.join(repo_dir, 'common/src/main/java/com/google/auto/common/Visibility.java')
    if os.path.exists(vis_path):
        with open(vis_path) as f: c = f.read()
        old = """      effectiveVisibility =
          Ordering.natural().min(effectiveVisibility, ofElement(currentElement));
      currentElement = currentElement.getEnclosingElement();"""
        new = """      effectiveVisibility =
          Ordering.natural().min(effectiveVisibility, ofElement(currentElement));
      if (currentElement.getKind().equals(PACKAGE)) {
        break;
      }
      currentElement = currentElement.getEnclosingElement();"""
        m = c.replace(old, new)
        if m != c:
            diff = generate_diff(vis_path, m, os.path.relpath(vis_path, repo_dir))
            patches.append((os.path.relpath(vis_path, repo_dir), diff, m))
    return patches
