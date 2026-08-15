---
name: evo-github-repo-analytics
description: "Generates a community pulse report for a GitHub repository by querying the GitHub Search API for PRs and issues within a date range, computing merge statistics, identifying top contributors, classifying bug reports by label substring, and counting resolved bugs. Use when asked to produce a JSON summary of repository activity."
---

# GitHub Repository Analytics Skill

This skill fetches PR and issue data from the GitHub Search API and produces a
structured JSON report with PR counts, merge statistics, top contributors,
bug report counts, and resolved bug counts.

## Key Concepts

- **Cohort selection**: PRs/issues are selected by `created` date range
- **PR states**: `merged` (has merged_at) vs `closed` (state=closed, no merged_at) are tracked separately
- **Merge duration**: `mergedAt - createdAt` in days, averaged and rounded to 1 decimal
- **Bug detection**: Any issue with at least one label containing substring 'bug' (case-insensitive)
- **Resolved bugs**: Bug issues whose `closed_at` falls within the specified period
- **Pagination**: Handles multi-page results (100 per page)
- **Top contributor**: By PR count, alphabetical tie-break

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-github-repo-analytics/scripts')
from utils import generate_report, validate_report

# Generate the report
report = generate_report(
    repo='cli/cli',
    start_date='2024-12-01',
    end_date='2024-12-31',
    output_path='/app/report.json'
)

# Validate the output
validate_report('/app/report.json')
```

## Output Format

```json
{
  "pr": {
    "total": "<int> PRs created in period",
    "merged": "<int> PRs merged (as of now)",
    "closed": "<int> PRs closed without merge (as of now)",
    "avg_merge_days": "<float> average days from creation to merge, 1 decimal",
    "top_contributor": "<str> GitHub login with most PRs created"
  },
  "issue": {
    "total": "<int> issues created in period",
    "bug": "<int> issues with a label containing 'bug'",
    "resolved_bugs": "<int> bug issues closed during the period"
  }
}
```

## Functions

- `fetch_all_search_results(repo, item_type, created_range)` - Paginated GitHub search
- `analyze_prs(items)` - Compute PR statistics from search results
- `analyze_issues(items, month_start, month_end)` - Compute issue statistics
- `generate_report(repo, start_date, end_date, output_path)` - End-to-end entry point
- `validate_report(report_path)` - Validate output JSON structure and types
