import json
import subprocess
import sys
from datetime import datetime


def run_curl(url):
    """Run curl and return parsed JSON."""
    result = subprocess.run(
        ['curl', '-s', url],
        capture_output=True, text=True, timeout=30
    )
    return json.loads(result.stdout)


def fetch_all_search_results(repo, item_type, created_range):
    """Fetch all search results for a repo, type, and date range.
    
    Args:
        repo: e.g. 'cli/cli'
        item_type: 'pr' or 'issue'
        created_range: e.g. '2024-12-01..2024-12-31'
    
    Returns:
        list of items
    """
    all_items = []
    page = 1
    while True:
        url = (f'https://api.github.com/search/issues?'
               f'q=repo:{repo}+type:{item_type}+created:{created_range}'
               f'&per_page=100&page={page}')
        data = run_curl(url)
        items = data.get('items', [])
        all_items.extend(items)
        if len(items) < 100:
            break
        page += 1
    return all_items


def analyze_prs(items):
    """Analyze PR items from search results.
    
    Returns dict with:
        total, merged, closed, avg_merge_days, top_contributor
    """
    total = len(items)
    merged_count = 0
    closed_not_merged = 0
    merge_days = []
    authors = {}
    
    for item in items:
        # Count author
        user = item['user']['login'] if item.get('user') else 'unknown'
        authors[user] = authors.get(user, 0) + 1
        
        # Check merge status
        pr_info = item.get('pull_request', {})
        merged_at = pr_info.get('merged_at')
        
        if merged_at:
            merged_count += 1
            created = datetime.strptime(item['created_at'], '%Y-%m-%dT%H:%M:%SZ')
            merged = datetime.strptime(merged_at, '%Y-%m-%dT%H:%M:%SZ')
            delta = (merged - created).total_seconds() / 86400.0
            merge_days.append(delta)
        elif item['state'] == 'closed':
            closed_not_merged += 1
    
    avg_merge = round(sum(merge_days) / len(merge_days), 1) if merge_days else 0.0
    
    # Top contributor: most PRs, tie-break alphabetically
    sorted_authors = sorted(authors.items(), key=lambda x: (-x[1], x[0]))
    top_contributor = sorted_authors[0][0] if sorted_authors else 'unknown'
    
    return {
        'total': total,
        'merged': merged_count,
        'closed': closed_not_merged,
        'avg_merge_days': avg_merge,
        'top_contributor': top_contributor
    }


def analyze_issues(items, month_start, month_end):
    """Analyze issue items from search results.
    
    Args:
        items: list of issue items from search
        month_start: datetime for start of period (inclusive)
        month_end: datetime for end of period (exclusive)
    
    Returns dict with:
        total, bug, resolved_bugs
    """
    total = len(items)
    bug_issues = []
    
    for item in items:
        labels = [l['name'] for l in item.get('labels', [])]
        is_bug = any('bug' in label.lower() for label in labels)
        if is_bug:
            bug_issues.append(item)
    
    # Count bugs closed during the specified period
    resolved_bugs = 0
    for item in bug_issues:
        closed_at = item.get('closed_at')
        if closed_at:
            closed_dt = datetime.strptime(closed_at, '%Y-%m-%dT%H:%M:%SZ')
            if closed_dt >= month_start and closed_dt < month_end:
                resolved_bugs += 1
    
    return {
        'total': total,
        'bug': len(bug_issues),
        'resolved_bugs': resolved_bugs
    }


def generate_report(repo, start_date, end_date, output_path):
    """End-to-end entry point: fetch data and generate report.json.
    
    Args:
        repo: GitHub repo in 'owner/repo' format
        start_date: 'YYYY-MM-DD' start of period (inclusive)
        end_date: 'YYYY-MM-DD' end of period (inclusive)
        output_path: path to write report.json
    """
    created_range = f'{start_date}..{end_date}'
    
    # Parse date boundaries for closure checks
    month_start = datetime.strptime(start_date, '%Y-%m-%d')
    # end_date is inclusive, so month_end is day after
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    month_end = datetime(end_dt.year, end_dt.month, end_dt.day + 1) if end_dt.day < 28 else \
                datetime(end_dt.year + (1 if end_dt.month == 12 else 0),
                         (end_dt.month % 12) + 1, 1)
    
    print(f"Fetching PRs for {repo} created {created_range}...")
    pr_items = fetch_all_search_results(repo, 'pr', created_range)
    pr_data = analyze_prs(pr_items)
    print(f"PR results: {pr_data}")
    
    print(f"Fetching issues for {repo} created {created_range}...")
    issue_items = fetch_all_search_results(repo, 'issue', created_range)
    issue_data = analyze_issues(issue_items, month_start, month_end)
    print(f"Issue results: {issue_data}")
    
    report = {
        'pr': pr_data,
        'issue': issue_data
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report written to {output_path}")
    return report


def validate_report(report_path):
    """Validate the report.json structure and types."""
    with open(report_path) as f:
        report = json.load(f)
    
    # Check required keys
    assert 'pr' in report, "Missing 'pr' key"
    assert 'issue' in report, "Missing 'issue' key"
    
    pr = report['pr']
    assert isinstance(pr['total'], int), "pr.total must be int"
    assert isinstance(pr['merged'], int), "pr.merged must be int"
    assert isinstance(pr['closed'], int), "pr.closed must be int"
    assert isinstance(pr['avg_merge_days'], (int, float)), "pr.avg_merge_days must be float"
    assert isinstance(pr['top_contributor'], str), "pr.top_contributor must be str"
    
    issue = report['issue']
    assert isinstance(issue['total'], int), "issue.total must be int"
    assert isinstance(issue['bug'], int), "issue.bug must be int"
    assert isinstance(issue['resolved_bugs'], int), "issue.resolved_bugs must be int"
    
    # Sanity checks
    assert pr['merged'] + pr['closed'] <= pr['total'], "merged + closed should not exceed total"
    assert issue['bug'] <= issue['total'], "bugs should not exceed total issues"
    assert issue['resolved_bugs'] <= issue['bug'], "resolved bugs should not exceed total bugs"
    
    print("Validation passed!")
    return True
