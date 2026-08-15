---
name: evo-suricata-http-exfil
description: "Generate and validate Suricata rules for detecting HTTP-based data exfiltration patterns. Use when the task requires writing Suricata signatures that match specific HTTP method, URI, headers, and body field patterns with regex validation. Supports incremental testing against positive/negative pcaps."
---

# Suricata HTTP Exfiltration Detection Rule Skill

This skill provides reusable functions for generating Suricata rules that detect
HTTP-based data exfiltration. It handles:

- Building rules with HTTP sticky buffers (http.method, http.uri, http.header, http.request_body)
- Exact URI matching with bsize
- Header name:value matching with CRLF boundary and optional case-insensitivity
- Body field matching with URL-encoded field boundary checks to prevent substring false positives
- Syntax validation via `suricata -T`
- Functional validation against positive/negative pcap files

## Key Technical Details

### HTTP Sticky Buffers
- `http.method` - matches the HTTP method (GET, POST, etc.)
- `http.uri` - matches the normalized URI path; use `bsize:N` for exact length
- `http.header` - matches raw request headers
- `http.request_body` - matches the HTTP request body

### Header Matching Best Practices
- HTTP header names are case-insensitive per RFC 7230; use `nocase` to handle variations
- Append `|0d 0a|` (CRLF) after the header value to prevent substring false positives
  (e.g., header value "exfil" should not match "exfiltrate")
- The `http.header` buffer contains raw headers as sent by the client

### Body Field Boundary Matching
In URL-encoded bodies (`application/x-www-form-urlencoded`), fields are separated
by `&` and the first field starts at the beginning of the body. A naive
`content:"blob="` would match `xblob=` as a substring.

The correct approach uses PCRE with field boundary checks:
```
pcre:"/(?:^|&)fieldname=VALUE_PATTERN/"
```
This ensures `fieldname` is either at the start of the body or preceded by `&`.

### PCRE with /R Flag
- `/R` means "relative to last content match"
- When not using a preceding content anchor, omit `/R` to search the entire buffer
- Use `(?:^|&)` for URL-encoded field boundary matching

### Common Pitfalls
- `bsize` must exactly equal the URI string length (count carefully)
- Content matches are substring matches; use field boundaries to prevent false positives
- Header names in `http.header` buffer are raw (not normalized for case)
- `flow:to_server,established` ensures we match client requests in established TCP sessions
- All conditions within a single rule are conjunctive (AND)

## Usage Example

The caller reads the task instruction, extracts detection requirements, and
passes them as parameters. Below is a synthetic example (not from any real task):

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-suricata-http-exfil/scripts')
from utils import generate_and_validate

# Example: detect a hypothetical beacon pattern on /api/v3/heartbeat
# with header X-App-Type: beacon, body containing token= (40+ alphanums)
# and checksum= (32 hex chars). Adapt all parameters from your task instruction.
#
# Note: body_fields[].regex is the VALUE pattern only; the function
# automatically adds (?:^|&)fieldname= boundary logic.
success, details = generate_and_validate(
    rules_path='/root/local.rules',
    suricata_yaml='/root/suricata.yaml',
    pcaps_dir='/root/pcaps/',
    sid=1000099,
    msg='Hypothetical beacon detection',
    method='POST',
    uri_path='/api/v3/heartbeat',
    header_name='X-App-Type',
    header_value='beacon',
    body_fields=[
        {'name': 'token', 'regex': '[A-Za-z0-9]{40,}'},
        {'name': 'checksum', 'regex': '[0-9a-f]{32}(&|$)'},
    ],
)

for line in details:
    print(line)

if success:
    print('\nAll validations passed!')
else:
    print('\nSome validations failed - check details above.')
    sys.exit(1)
```

## Individual Functions

- `build_http_exfil_rule(sid, msg, method, uri_path, header_name, header_value, body_fields, rev, header_nocase)` - Build a single Suricata rule string
- `write_rules_file(rules_path, rules)` - Write rules to a file
- `validate_rule_syntax(rules_path, suricata_yaml)` - Check rule syntax
- `run_suricata_on_pcap(pcap, rules_path, yaml, log_dir)` - Run against a pcap
- `validate_rule_against_pcaps(rules_path, yaml, pos_pcaps, neg_pcaps, sid)` - Test against pos/neg pcaps
- `generate_and_validate(rules_path, yaml, pcaps_dir, sid, msg, method, uri_path, header_name, header_value, body_fields, rev, header_nocase)` - End-to-end entry point
