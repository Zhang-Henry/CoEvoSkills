"""Validate the output of the LongestSessionPerJob Flink job.

Checks:
- Output file exists and is non-empty
- Each line matches format (jobId,count)
- No duplicate jobIds
- All counts are positive integers
- All jobIds are valid longs
"""
import re
import sys


def validate_output_format(output_path):
    """Validate the output file format and content.
    
    Args:
        output_path: Path to the output file
    Returns:
        dict with 'valid' (bool), 'line_count' (int), 'errors' (list of str)
    """
    errors = []
    job_ids = set()
    line_count = 0
    pattern = re.compile(r'^\((\d+),(\d+)\)$')
    
    try:
        with open(output_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                line_count += 1
                m = pattern.match(line)
                if not m:
                    errors.append(f"Line {line_num}: Invalid format: {line}")
                    continue
                job_id = int(m.group(1))
                count = int(m.group(2))
                if count <= 0:
                    errors.append(f"Line {line_num}: Count must be positive: {count}")
                if job_id in job_ids:
                    errors.append(f"Line {line_num}: Duplicate jobId: {job_id}")
                job_ids.add(job_id)
    except FileNotFoundError:
        errors.append(f"Output file not found: {output_path}")
        return {'valid': False, 'line_count': 0, 'errors': errors}
    
    if line_count == 0:
        errors.append("Output file is empty")
    
    result = {
        'valid': len(errors) == 0,
        'line_count': line_count,
        'unique_jobs': len(job_ids),
        'errors': errors
    }
    
    if result['valid']:
        print(f"VALID: {line_count} lines, {len(job_ids)} unique jobs")
    else:
        print(f"INVALID: {len(errors)} errors found")
        for e in errors[:10]:
            print(f"  - {e}")
    
    return result


def validate_against_data(output_path, task_input, job_input):
    """Cross-validate output against input data files.
    
    Verifies that:
    - Every jobId in output has a FINISH event in job_events
    - Every jobId in output has SUBMIT events in task_events
    
    Args:
        output_path: Path to the output file
        task_input: Path to gzipped task events CSV
        job_input: Path to gzipped job events CSV
    Returns:
        dict with validation results
    """
    import gzip
    
    # Parse output
    output_jobs = {}
    with open(output_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Parse (jobId,count)
            inner = line[1:-1]  # strip parens
            parts = inner.split(',')
            output_jobs[int(parts[0])] = int(parts[1])
    
    # Get finished jobs from job events
    finished_jobs = set()
    with gzip.open(job_input, 'rt') as f:
        for line in f:
            parts = line.strip().split(',', 5)
            if len(parts) >= 4 and parts[3] == '4':
                try:
                    finished_jobs.add(int(parts[2]))
                except ValueError:
                    pass
    
    # Get jobs with SUBMIT events
    submit_jobs = set()
    with gzip.open(task_input, 'rt') as f:
        for line in f:
            parts = line.strip().split(',', 7)
            if len(parts) >= 6 and parts[5] == '0':
                try:
                    submit_jobs.add(int(parts[2]))
                except ValueError:
                    pass
    
    # Validate
    errors = []
    expected_jobs = finished_jobs & submit_jobs
    
    for job_id in output_jobs:
        if job_id not in finished_jobs:
            errors.append(f"Job {job_id} in output but not finished")
        if job_id not in submit_jobs:
            errors.append(f"Job {job_id} in output but has no SUBMIT events")
    
    missing = expected_jobs - set(output_jobs.keys())
    if missing:
        errors.append(f"{len(missing)} expected jobs missing from output")
    
    extra = set(output_jobs.keys()) - expected_jobs
    if extra:
        errors.append(f"{len(extra)} unexpected jobs in output")
    
    result = {
        'valid': len(errors) == 0,
        'output_count': len(output_jobs),
        'finished_count': len(finished_jobs),
        'submit_jobs_count': len(submit_jobs),
        'expected_count': len(expected_jobs),
        'errors': errors
    }
    
    if result['valid']:
        print(f"CROSS-VALIDATION PASSED: {len(output_jobs)} jobs match expected {len(expected_jobs)}")
    else:
        print(f"CROSS-VALIDATION FAILED:")
        for e in errors[:10]:
            print(f"  - {e}")
    
    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python validate_output.py <output_path> [task_input] [job_input]")
        sys.exit(1)
    
    result = validate_output_format(sys.argv[1])
    if not result['valid']:
        sys.exit(1)
    
    if len(sys.argv) >= 4:
        result2 = validate_against_data(sys.argv[1], sys.argv[2], sys.argv[3])
        if not result2['valid']:
            sys.exit(1)

