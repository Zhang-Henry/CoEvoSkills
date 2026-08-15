"""Utility functions for dependency security auditing using trivy."""

import json
import csv
import subprocess
import os


def run_trivy_scan(lockfile_path, severity_levels=None, output_json_path=None):
    """Run trivy filesystem scan on a dependency lockfile.
    
    Args:
        lockfile_path: Path to the package-lock.json or similar lockfile
        severity_levels: List of severity levels to filter (e.g., ['HIGH', 'CRITICAL'])
        output_json_path: Optional path to save raw JSON output
    
    Returns:
        dict: Parsed trivy JSON output
    """
    if severity_levels is None:
        severity_levels = ['HIGH', 'CRITICAL']
    
    severity_str = ','.join(severity_levels)
    
    cmd = [
        'trivy', 'fs',
        '--scanners', 'vuln',
        '--severity', severity_str,
        '--format', 'json',
        '--skip-db-update',
        '--offline-scan',
        lockfile_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0 and not result.stdout:
        raise RuntimeError(f"Trivy scan failed: {result.stderr}")
    
    data = json.loads(result.stdout)
    
    if output_json_path:
        with open(output_json_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    return data


def extract_vulnerabilities(trivy_data):
    """Extract vulnerability records from trivy JSON output.
    
    Args:
        trivy_data: Parsed trivy JSON output dict
    
    Returns:
        list: List of raw vulnerability dicts from trivy
    """
    vulns = []
    for result in trivy_data.get('Results', []):
        for v in result.get('Vulnerabilities', []):
            vulns.append(v)
    return vulns


def get_cvss_score(vuln):
    """Extract CVSS score from a vulnerability record.
    
    Uses the severity source as primary, then falls back through
    ghsa -> nvd -> redhat -> any available source.
    Per reproducibility doc: take fields from one coherent source record.
    
    Args:
        vuln: Trivy vulnerability dict
    
    Returns:
        float or str: CVSS V3 score, or empty string if not available
    """
    severity_source = vuln.get('SeveritySource', '')
    cvss_data = vuln.get('CVSS', {})
    
    # Try severity source first for coherent record
    if severity_source in cvss_data and 'V3Score' in cvss_data[severity_source]:
        return cvss_data[severity_source]['V3Score']
    
    # Fallback order
    for source in ['ghsa', 'nvd', 'redhat']:
        if source in cvss_data and 'V3Score' in cvss_data[source]:
            return cvss_data[source]['V3Score']
    
    # Any available source
    for source in cvss_data:
        if 'V3Score' in cvss_data[source]:
            return cvss_data[source]['V3Score']
    
    return ''


def format_vulnerability_row(vuln):
    """Format a trivy vulnerability dict into a CSV row dict.
    
    Args:
        vuln: Trivy vulnerability dict
    
    Returns:
        dict: Row with keys matching CSV columns
    """
    fixed_version = vuln.get('FixedVersion', '') or 'N/A'
    if not fixed_version.strip():
        fixed_version = 'N/A'
    
    return {
        'Package': vuln.get('PkgName', ''),
        'Version': vuln.get('InstalledVersion', ''),
        'CVE_ID': vuln.get('VulnerabilityID', ''),
        'Severity': vuln.get('Severity', ''),
        'CVSS_Score': get_cvss_score(vuln),
        'Fixed_Version': fixed_version,
        'Title': vuln.get('Title', vuln.get('Description', '')),
        'Url': vuln.get('PrimaryURL', '')
    }


def deduplicate_rows(rows):
    """Deduplicate vulnerability rows by (Package, Version, CVE_ID).
    
    Args:
        rows: List of row dicts
    
    Returns:
        list: Deduplicated list of row dicts
    """
    seen = set()
    unique = []
    for row in rows:
        key = (row['Package'], row['Version'], row['CVE_ID'])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def sort_rows(rows):
    """Sort rows deterministically by Package, CVE_ID.
    
    Args:
        rows: List of row dicts
    
    Returns:
        list: Sorted list of row dicts
    """
    return sorted(rows, key=lambda x: (x['Package'], x['CVE_ID']))


def write_csv(rows, output_path):
    """Write vulnerability rows to CSV file.
    
    Args:
        rows: List of row dicts
        output_path: Path for output CSV file
    """
    fieldnames = ['Package', 'Version', 'CVE_ID', 'Severity', 'CVSS_Score',
                  'Fixed_Version', 'Title', 'Url']
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_audit(lockfile_path, output_csv_path, severity_levels=None):
    """End-to-end entry point: scan lockfile and produce CSV audit report.
    
    Args:
        lockfile_path: Path to package-lock.json
        output_csv_path: Path for output CSV file
        severity_levels: List of severity levels (default: ['HIGH', 'CRITICAL'])
    
    Returns:
        list: The rows written to CSV
    """
    if severity_levels is None:
        severity_levels = ['HIGH', 'CRITICAL']
    
    # Run trivy scan
    trivy_data = run_trivy_scan(lockfile_path, severity_levels)
    
    # Extract vulnerabilities
    vulns = extract_vulnerabilities(trivy_data)
    
    # Format rows
    rows = [format_vulnerability_row(v) for v in vulns]
    
    # Deduplicate
    rows = deduplicate_rows(rows)
    
    # Sort deterministically
    rows = sort_rows(rows)
    
    # Write CSV
    write_csv(rows, output_csv_path)
    
    return rows


def validate_audit(csv_path):
    """Validate the audit CSV file meets requirements.
    
    Args:
        csv_path: Path to the CSV file to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        AssertionError: If validation fails
    """
    assert os.path.exists(csv_path), f"CSV file not found: {csv_path}"
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        expected = ['Package', 'Version', 'CVE_ID', 'Severity', 'CVSS_Score',
                    'Fixed_Version', 'Title', 'Url']
        assert fieldnames == expected, f"Wrong columns: {fieldnames}, expected: {expected}"
        
        rows = list(reader)
        assert len(rows) > 0, "No vulnerability rows found"
        
        for i, row in enumerate(rows):
            assert row['Package'], f"Row {i}: Missing Package"
            assert row['Version'], f"Row {i}: Missing Version"
            assert row['CVE_ID'].startswith('CVE-'), f"Row {i}: Invalid CVE_ID: {row['CVE_ID']}"
            assert row['Severity'] in ('HIGH', 'CRITICAL'), f"Row {i}: Invalid Severity: {row['Severity']}"
            assert row['CVSS_Score'], f"Row {i}: Missing CVSS_Score"
            assert float(row['CVSS_Score']) >= 0, f"Row {i}: Invalid CVSS_Score"
            assert row['Fixed_Version'], f"Row {i}: Missing Fixed_Version"
            assert row['Title'], f"Row {i}: Missing Title"
            assert row['Url'], f"Row {i}: Missing Url"
        
        # Check deterministic ordering
        keys = [(r['Package'], r['CVE_ID']) for r in rows]
        assert keys == sorted(keys), "Rows not in deterministic order"
        
        # Check no duplicates
        dedup_keys = [(r['Package'], r['Version'], r['CVE_ID']) for r in rows]
        assert len(dedup_keys) == len(set(dedup_keys)), "Duplicate rows found"
    
    print(f"Validation passed: {len(rows)} vulnerabilities in {csv_path}")
    return True
