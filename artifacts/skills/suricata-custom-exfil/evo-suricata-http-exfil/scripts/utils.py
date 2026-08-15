import subprocess
import os
import re
import glob


def build_http_exfil_rule(
    sid,
    msg,
    method,
    uri_path,
    header_name,
    header_value,
    body_fields,
    rev=1,
    header_nocase=True,
):
    """
    Build a Suricata rule that detects HTTP-based data exfiltration.

    Parameters:
        sid: Suricata signature ID (int)
        msg: Alert message string
        method: HTTP method to match (e.g., 'POST', 'GET')
        uri_path: Exact URI path to match (e.g., '/api/v1/data')
        header_name: Header name to check (e.g., 'X-Custom-Header')
        header_value: Expected header value (e.g., 'suspicious')
        body_fields: List of dicts, each with:
            - 'name': field name in URL-encoded body (e.g., 'data')
            - 'regex': PCRE pattern for the field value (e.g., '[A-Za-z0-9]{40,}')
              The regex should match the VALUE only; the function adds field
              boundary logic (^|&) and the field name prefix automatically.
        rev: Rule revision number
        header_nocase: If True, match header case-insensitively (recommended
            since HTTP header names are case-insensitive per RFC 7230)

    Returns the rule as a string.
    """
    uri_len = len(uri_path)

    opts = []
    opts.append(f'msg:"{msg}"')
    opts.append('flow:to_server,established')

    # HTTP method
    opts.append('http.method')
    opts.append(f'content:"{method}"')

    # URI exact match using bsize for precision
    opts.append('http.uri')
    opts.append(f'content:"{uri_path}"')
    opts.append(f'bsize:{uri_len}')

    # Header match with CRLF boundary to prevent substring false positives
    # (e.g., 'exfil' should not match 'exfiltrate')
    opts.append('http.header')
    header_str = f'{header_name.lower()}: {header_value}|0d 0a|'
    opts.append(f'content:"{header_str}"')
    if header_nocase:
        opts.append('nocase')

    # Body fields using PCRE with field boundary checks.
    # In URL-encoded bodies, fields are separated by '&' and the first
    # field starts at the beginning of the body. Using (?:^|&) before
    # the field name prevents substring false positives (e.g., 'xblob'
    # matching a rule looking for 'blob').
    opts.append('http.request_body')
    for field in body_fields:
        field_pcre = f'(?:^|&){field["name"]}={field["regex"]}'
        opts.append(f'pcre:"/{field_pcre}/"')

    # Metadata
    opts.append(f'sid:{sid}')
    opts.append(f'rev:{rev}')

    opts_str = '; '.join(opts) + ';'
    rule = f'alert http any any -> any any ({opts_str})'
    return rule


def write_rules_file(rules_path, rules):
    """
    Write a list of rule strings to a Suricata rules file.
    """
    with open(rules_path, 'w') as f:
        for rule in rules:
            f.write(rule + '\n')
    return rules_path


def validate_rule_syntax(rules_path, suricata_yaml):
    """
    Run suricata -T to validate rule syntax.
    Returns (success: bool, output: str).
    """
    cmd = [
        'suricata', '-T',
        '-c', suricata_yaml,
        '-S', rules_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    combined = result.stdout + result.stderr
    success = 'Configuration provided was successfully loaded' in combined
    return success, combined


def run_suricata_on_pcap(pcap_path, rules_path, suricata_yaml, log_dir='/var/log/suricata/'):
    """
    Run Suricata against a pcap file and return alerts.
    Returns list of alert lines from fast.log.
    """
    fast_log = os.path.join(log_dir, 'fast.log')
    eve_log = os.path.join(log_dir, 'eve.json')
    for f in [fast_log, eve_log]:
        if os.path.exists(f):
            os.remove(f)

    cmd = [
        'suricata',
        '-r', pcap_path,
        '-c', suricata_yaml,
        '-S', rules_path,
        '-l', log_dir,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    alerts = []
    if os.path.exists(fast_log):
        with open(fast_log) as f:
            alerts = [line.strip() for line in f if line.strip()]

    return alerts


def validate_rule_against_pcaps(
    rules_path,
    suricata_yaml,
    positive_pcaps,
    negative_pcaps,
    expected_sid,
):
    """
    Validate that the rule alerts on positive pcaps and does NOT alert on negative pcaps.
    Returns (all_passed: bool, details: list of str).
    """
    details = []
    all_passed = True

    for pcap in positive_pcaps:
        alerts = run_suricata_on_pcap(pcap, rules_path, suricata_yaml)
        sid_found = any(f'[1:{expected_sid}:' in a for a in alerts)
        if sid_found:
            details.append(f'PASS: {pcap} - alert triggered for sid:{expected_sid}')
        else:
            details.append(f'FAIL: {pcap} - NO alert for sid:{expected_sid}')
            all_passed = False

    for pcap in negative_pcaps:
        alerts = run_suricata_on_pcap(pcap, rules_path, suricata_yaml)
        sid_found = any(f'[1:{expected_sid}:' in a for a in alerts)
        if not sid_found:
            details.append(f'PASS: {pcap} - no false positive')
        else:
            details.append(f'FAIL: {pcap} - false positive for sid:{expected_sid}')
            all_passed = False

    return all_passed, details


def generate_and_validate(
    rules_path,
    suricata_yaml,
    pcaps_dir,
    sid,
    msg,
    method,
    uri_path,
    header_name,
    header_value,
    body_fields,
    rev=1,
    header_nocase=True,
):
    """
    End-to-end entry point: generate a Suricata rule, write it, validate syntax,
    and test against pcaps in the given directory.

    All detection parameters must be supplied by the caller based on their
    task instruction. No defaults are assumed for detection logic.

    pcaps_dir is scanned for files matching *pos* (positive) and *neg* (negative).

    Returns (success: bool, details: list of str).
    """
    rule = build_http_exfil_rule(
        sid=sid,
        msg=msg,
        method=method,
        uri_path=uri_path,
        header_name=header_name,
        header_value=header_value,
        body_fields=body_fields,
        rev=rev,
        header_nocase=header_nocase,
    )

    write_rules_file(rules_path, [rule])

    details = [f'Rule written to {rules_path}:', rule]

    syntax_ok, syntax_out = validate_rule_syntax(rules_path, suricata_yaml)
    if syntax_ok:
        details.append('Syntax validation: PASSED')
    else:
        details.append(f'Syntax validation: FAILED\n{syntax_out}')
        return False, details

    pos_pcaps = sorted(glob.glob(os.path.join(pcaps_dir, '*pos*')))
    neg_pcaps = sorted(glob.glob(os.path.join(pcaps_dir, '*neg*')))

    if pos_pcaps or neg_pcaps:
        passed, test_details = validate_rule_against_pcaps(
            rules_path, suricata_yaml, pos_pcaps, neg_pcaps, sid
        )
        details.extend(test_details)
        return passed, details
    else:
        details.append('No training pcaps found - skipping pcap validation')
        return syntax_ok, details
