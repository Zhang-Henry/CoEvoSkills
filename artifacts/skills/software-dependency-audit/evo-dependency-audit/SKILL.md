---
name: evo-dependency-audit
description: "Perform security audit on npm/node dependency lockfiles using trivy offline scanner. Identifies HIGH and CRITICAL vulnerabilities and produces a structured CSV report with package, version, CVE, severity, CVSS score, fixed version, title, and reference URL."
---

# Dependency Security Audit Skill

This skill scans npm package-lock.json files for known vulnerabilities using
trivy's offline vulnerability database and produces a CSV audit report.

## Key Concepts

- Uses trivy filesystem scanner with offline DB (no network needed)
- Filters by severity level (HIGH, CRITICAL by default)
- Extracts CVSS scores from the severity source for coherent records
- Deterministic output ordering and deduplication
- Preserves missing fixed versions as "N/A"

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dependency-audit/scripts')
from utils import run_audit, validate_audit

# Run the full audit pipeline
rows = run_audit(
    lockfile_path='/root/package-lock.json',
    output_csv_path='/root/security_audit.csv',
    severity_levels=['HIGH', 'CRITICAL']
)
print(f"Found {len(rows)} vulnerabilities")

# Validate the output
validate_audit('/root/security_audit.csv')
```

## Individual Functions

All functions are in `scripts/utils.py`:

- `run_trivy_scan(lockfile_path, severity_levels, output_json_path)` - Run trivy scan
- `extract_vulnerabilities(trivy_data)` - Extract vulns from trivy JSON
- `get_cvss_score(vuln)` - Get CVSS score using coherent source priority
- `format_vulnerability_row(vuln)` - Format a vuln into a CSV row dict
- `deduplicate_rows(rows)` - Remove duplicate entries
- `sort_rows(rows)` - Deterministic sorting by Package, CVE_ID
- `write_csv(rows, output_path)` - Write CSV with proper headers
- `run_audit(lockfile_path, output_csv_path, severity_levels)` - End-to-end entry point
- `validate_audit(csv_path)` - Validate output CSV meets requirements

## CSV Output Format

Columns: `Package,Version,CVE_ID,Severity,CVSS_Score,Fixed_Version,Title,Url`

## CVSS Score Resolution

1. Use the severity source (usually ghsa) for coherent record
2. Fallback: ghsa -> nvd -> redhat -> any available
3. Always use V3Score when available
