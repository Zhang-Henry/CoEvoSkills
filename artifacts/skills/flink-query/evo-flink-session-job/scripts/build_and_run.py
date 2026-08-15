"""Build and run the Flink LongestSessionPerJob job.

Provides functions to:
- Build the Maven project
- Start Flink cluster
- Submit and run the Flink job
- Validate the output
"""
import subprocess
import os
import sys


def build_maven_project(workspace_dir):
    """Build the Maven project and produce the JAR.
    
    Args:
        workspace_dir: Path to workspace root containing pom.xml
    Returns:
        Path to the built JAR file
    """
    print(f"Building Maven project in {workspace_dir}...")
    result = subprocess.run(
        ['mvn', 'clean', 'package', '-DskipTests'],
        cwd=workspace_dir,
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print("BUILD FAILED:")
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        raise RuntimeError("Maven build failed")
    
    jar_path = os.path.join(workspace_dir, 'target', 'LongestSessionPerJob-jar-with-dependencies.jar')
    if not os.path.exists(jar_path):
        raise FileNotFoundError(f"JAR not found at {jar_path}")
    print(f"Build successful: {jar_path}")
    return jar_path


def ensure_flink_running(flink_home='/opt/flink'):
    """Start Flink cluster if not already running.
    
    Args:
        flink_home: Path to Flink installation
    """
    start_script = os.path.join(flink_home, 'bin', 'start-cluster.sh')
    if os.path.exists(start_script):
        result = subprocess.run([start_script], capture_output=True, text=True, timeout=30)
        print(result.stdout)
    else:
        print(f"Warning: Flink start script not found at {start_script}")


def run_flink_job(jar_path, task_input, job_input, output_path, flink_home='/opt/flink'):
    """Submit and run the Flink job.
    
    Args:
        jar_path: Path to the built JAR
        task_input: Path to gzipped task events CSV
        job_input: Path to gzipped job events CSV
        output_path: Path for output file
        flink_home: Path to Flink installation
    Returns:
        Path to output file
    """
    flink_bin = os.path.join(flink_home, 'bin', 'flink')
    cmd = [
        flink_bin, 'run', jar_path,
        '--task_input', task_input,
        '--job_input', job_input,
        '--output', output_path
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print(result.stdout)
    if result.returncode != 0:
        print("JOB FAILED:")
        print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
        raise RuntimeError("Flink job failed")
    
    if not os.path.exists(output_path):
        raise FileNotFoundError(f"Output not found at {output_path}")
    print(f"Output written to {output_path}")
    return output_path


def run_end_to_end(workspace_dir, task_input, job_input, output_path, flink_home='/opt/flink'):
    """End-to-end: generate sources, build, start Flink, run job.
    
    Args:
        workspace_dir: Path to workspace root
        task_input: Path to gzipped task events CSV
        job_input: Path to gzipped job events CSV  
        output_path: Path for output file
        flink_home: Path to Flink installation
    Returns:
        Path to output file
    """
    # Import and run source generation
    from generate_java_sources import write_java_sources
    write_java_sources(workspace_dir)
    
    # Build
    jar_path = build_maven_project(workspace_dir)
    
    # Start Flink
    ensure_flink_running(flink_home)
    
    # Run job
    return run_flink_job(jar_path, task_input, job_input, output_path, flink_home)

