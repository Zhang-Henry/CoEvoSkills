"""
Test suite for Apache Druid CVE-2021-25646 vulnerability fix validation.

CVE-2021-25646 is a specific vulnerability where:
1. Jackson deserialization allows an empty string key ("") to override JavaScriptConfig
2. This enables JavaScript execution even when disabled by default
3. The attacker can then execute arbitrary code via the "function" field

This test sends multiple exploit payloads and verifies they are all blocked.
"""

import os
import secrets
import subprocess
from pathlib import Path


def _response_body(response):
    """Return response text plus any JSON body in a stable, searchable form."""
    text = response.text or ""
    try:
        payload = response.json()
    except (TypeError, ValueError):
        payload = None
    return text, payload


def _assert_successful_sample(response, expected_value):
    """Require a real sampler result, not merely the absence of an error word."""
    text, payload = _response_body(response)

    assert response.status_code == 200, (
        "A legitimate sampler request must succeed with HTTP 200; "
        f"got {response.status_code}: {text[:300]}"
    )
    assert isinstance(payload, dict), (
        "A legitimate sampler request must return a JSON object; "
        f"got: {text[:300]}"
    )
    assert payload.get("numRowsRead") == 1, (
        "Sampler did not read the single legitimate input row: "
        f"{payload}"
    )
    assert payload.get("numRowsIndexed") == 1, (
        "Sampler did not index the single legitimate input row: "
        f"{payload}"
    )

    rows = payload.get("data")
    assert isinstance(rows, list) and len(rows) == 1, (
        "Sampler must return exactly one result row for the one-row control input: "
        f"{payload}"
    )
    row = rows[0]
    assert isinstance(row, dict), f"Sampler result row is malformed: {row!r}"
    assert row.get("unparseable") in (None, False), (
        f"Legitimate control row was marked unparseable: {row}"
    )
    assert not row.get("error"), f"Legitimate control row returned an error: {row}"

    input_row = row.get("input")
    parsed_row = row.get("parsed")
    assert isinstance(input_row, dict) and input_row.get("value") == expected_value, (
        "Sampler response did not preserve the control value in the input row: "
        f"{row}"
    )
    assert isinstance(parsed_row, dict) and parsed_row.get("value") == expected_value, (
        "Sampler response did not preserve the control value in the parsed row: "
        f"{row}"
    )


def _assert_explicit_exploit_rejection(response, payload_info):
    """Require an explicit security rejection, not a generic broken endpoint."""
    text, payload = _response_body(response)
    normalized = text.lower()

    assert 400 <= response.status_code < 600, (
        f"Exploit {payload_info['name']} was not rejected with an error status; "
        f"got {response.status_code}: {text[:300]}"
    )

    # Druid 0.20 may map the thrown validation exception to either a 4xx or a
    # 5xx response. In both cases the body must say why this request was
    # rejected. Generic service failures are not evidence of a security fix.
    rejection_markers = (
        "javascript is disabled",
        "javascript disabled",
        "javascript is not enabled",
        "javascript not enabled",
        "empty key",
        "invalid request",
        "not allowed",
        "forbidden",
        "rejected",
        "cve-2021-25646",
    )
    assert any(marker in normalized for marker in rejection_markers), (
        f"Exploit {payload_info['name']} failed only generically rather than "
        f"being explicitly rejected: status={response.status_code}, body={text[:300]}"
    )

    if isinstance(payload, dict):
        assert not (
            payload.get("numRowsRead") == 1
            and payload.get("numRowsIndexed") == 1
            and payload.get("data")
        ), (
            f"Exploit {payload_info['name']} returned a successful sampler result: "
            f"{payload}"
        )

    # A non-2xx response with an explicit security explanation is the protocol
    # signal. Avoid ambiguous output words such as "root", which can occur in
    # harmless server paths or generated error pages. The separate randomized
    # filesystem probe below verifies that JavaScript did not execute at all.
    assert "uid=" not in normalized and "gid=" not in normalized, (
        f"Exploit {payload_info['name']} exposed process identity output: {text[:300]}"
    )


def test_patches_exist():
    """Test that patch files were created."""
    workspace = os.getenv("WORKSPACE", "/root")
    patches_dir = Path(workspace) / "patches"

    assert patches_dir.exists(), "Patches directory not found"

    patch_files = list(patches_dir.glob("*.patch"))
    assert len(patch_files) > 0, "No patch files found"


def test_patches_applied():
    """Test that patches were applied to the Druid source code."""
    workspace = os.getenv("WORKSPACE", "/root")
    druid_dir = Path(workspace) / "druid"

    assert druid_dir.exists(), "Druid source directory not found"

    result = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=druid_dir,
        capture_output=True,
        text=True,
        timeout=10
    )

    modified_files = [f for f in result.stdout.strip().split("\n") if f]
    assert len(modified_files) > 0, "No files were modified. Patches must be applied."


def get_exploit_payloads():
    """
    Generate multiple CVE-2021-25646 exploit payloads with different commands.

    All payloads use the same vulnerability mechanism:
    - Empty string key ("") in JSON overrides JavaScriptConfig
    - This enables JavaScript execution bypassing server config

    We test with different malicious JavaScript functions to ensure
    the fix blocks the vulnerability itself, not just specific commands.
    """
    payloads = []

    # Payload 1: Execute 'id' command (classic RCE test)
    payloads.append({
        "name": "rce_id_command",
        "description": "Execute 'id' command via Runtime.exec()",
        "rce_indicator": "uid=",
        "js_function": (
            "function(){var a = new java.util.Scanner("
            "java.lang.Runtime.getRuntime().exec(['sh','-c','id']).getInputStream()"
            ").useDelimiter('\\\\A').next();return {timestamp:123123,test: a}}"
        )
    })

    # Payload 2: Execute 'whoami' command
    payloads.append({
        "name": "rce_whoami_command",
        "description": "Execute 'whoami' command via Runtime.exec()",
        "rce_indicator": "root",  # Expected output on most systems
        "js_function": (
            "function(){var a = new java.util.Scanner("
            "java.lang.Runtime.getRuntime().exec(['sh','-c','whoami']).getInputStream()"
            ").useDelimiter('\\\\A').next();return {timestamp:123123,test: a}}"
        )
    })

    # Payload 3: Execute 'hostname' command
    payloads.append({
        "name": "rce_hostname_command",
        "description": "Execute 'hostname' command via Runtime.exec()",
        "rce_indicator": None,  # Can't predict hostname, just check for success
        "js_function": (
            "function(){var a = new java.util.Scanner("
            "java.lang.Runtime.getRuntime().exec(['sh','-c','hostname']).getInputStream()"
            ").useDelimiter('\\\\A').next();return {timestamp:123123,test: a}}"
        )
    })

    # Payload 4: Read /etc/passwd (file read attack)
    payloads.append({
        "name": "file_read_etc_passwd",
        "description": "Read /etc/passwd via Runtime.exec('cat')",
        "rce_indicator": "/bin/bash",  # Common in /etc/passwd
        "js_function": (
            "function(){var a = new java.util.Scanner("
            "java.lang.Runtime.getRuntime().exec(['sh','-c','cat /etc/passwd']).getInputStream()"
            ").useDelimiter('\\\\A').next();return {timestamp:123123,test: a}}"
        )
    })

    # Payload 5: Environment variable exfiltration
    payloads.append({
        "name": "env_exfiltration",
        "description": "Exfiltrate environment variables via 'env' command",
        "rce_indicator": "PATH=",  # PATH is always set
        "js_function": (
            "function(){var a = new java.util.Scanner("
            "java.lang.Runtime.getRuntime().exec(['sh','-c','env']).getInputStream()"
            ").useDelimiter('\\\\A').next();return {timestamp:123123,test: a}}"
        )
    })

    # Payload 6: Using ProcessBuilder instead of Runtime.exec
    payloads.append({
        "name": "rce_processbuilder",
        "description": "Execute command via ProcessBuilder",
        "rce_indicator": "uid=",
        "js_function": (
            "function(){var pb = new java.lang.ProcessBuilder(['sh','-c','id']);"
            "var p = pb.start();"
            "var a = new java.util.Scanner(p.getInputStream()).useDelimiter('\\\\A').next();"
            "return {timestamp:123123,test: a}}"
        )
    })

    # Payload 7: a randomized out-of-band side effect. This catches an
    # implementation that executes JavaScript and then fabricates an error
    # response containing a security-looking message.
    side_effect_path = f"/tmp/druid-cve-probe-{secrets.token_hex(12)}"
    payloads.append({
        "name": "filesystem_side_effect_probe",
        "description": "Create a verifier-randomized file via Runtime.exec()",
        "rce_indicator": None,
        "side_effect_path": side_effect_path,
        "js_function": (
            "function(){java.lang.Runtime.getRuntime().exec("
            f"['sh','-c','touch {side_effect_path}']"
            ");return {timestamp:123123,test:'completed'}}"
        )
    })

    return payloads


def build_exploit_request(js_function):
    """Build the full exploit request payload with the given JavaScript function."""
    return {
        "type": "index",
        "spec": {
            "type": "index",
            "ioConfig": {
                "type": "index",
                "inputSource": {
                    "type": "inline",
                    "data": "{\"timestamp\":\"2021-01-01T00:00:00Z\",\"test\":\"aaa\"}"
                },
                "inputFormat": {
                    "type": "json"
                }
            },
            "dataSchema": {
                "dataSource": "test",
                "timestampSpec": {
                    "column": "timestamp",
                    "format": "auto"
                },
                "dimensionsSpec": {},
                "transformSpec": {
                    "filter": {
                        "type": "javascript",
                        "dimension": "test",
                        "function": js_function,
                        # Empty key injection - the CVE-2021-25646 trick
                        # This overrides JavaScriptConfig to enable JS execution
                        "": {
                            "enabled": True
                        }
                    }
                }
            }
        },
        "samplerConfig": {
            "numRows": 10,
            "timeoutMs": 15000
        }
    }


def test_legitimate_requests_still_work():
    """
    Test that legitimate (non-JavaScript) sampler requests still work.

    This ensures the fix doesn't just block the entire endpoint,
    but specifically validates and blocks JavaScript code.
    """
    druid_host = os.getenv("DRUID_HOST", "localhost")
    druid_port = int(os.getenv("DRUID_PORT", "8888"))

    # Use a verifier-generated value so a hard-coded or synthetic success
    # response cannot satisfy the functional control.
    control_value = f"control-{secrets.token_hex(8)}"

    # Legitimate request with JSON parser (no JavaScript)
    legitimate_payload = {
        "type": "index",
        "spec": {
            "type": "index",
            "ioConfig": {
                "type": "index",
                "inputSource": {
                    "type": "inline",
                    "data": (
                        '{"timestamp":"2021-01-01T00:00:00Z","value":"'
                        + control_value
                        + '"}'
                    )
                },
                "inputFormat": {
                    "type": "json"
                }
            },
            "dataSchema": {
                "dataSource": "test",
                "timestampSpec": {
                    "column": "timestamp",
                    "format": "auto"
                },
                "dimensionsSpec": {}
            }
        },
        "samplerConfig": {
            "numRows": 10,
            "timeoutMs": 15000
        }
    }

    try:
        import requests

        url = f"http://{druid_host}:{druid_port}/druid/indexer/v1/sampler"

        response = requests.post(
            url,
            json=legitimate_payload,
            headers={"Content-Type": "application/json"},
            timeout=20
        )

        _assert_successful_sample(response, control_value)

        print(
            "✓ Legitimate request produced the expected semantic sampler result "
            f"(status: {response.status_code})"
        )

    except requests.exceptions.ConnectionError:
        assert False, (
            f"Cannot connect to Druid server at {druid_host}:{druid_port}. "
            "The patched Druid must be running."
        )


def test_cve_2021_25646_exploits_blocked():
    """
    DEFINITIVE TEST: Send multiple CVE-2021-25646 exploit variants and verify ALL are blocked.

    The CVE-2021-25646 exploit uses:
    1. "type": "javascript" filter
    2. Empty key "" with {"enabled": true} to bypass JavaScript disabled setting
    3. Malicious JavaScript function that executes system commands

    We test with multiple different commands to ensure the fix blocks
    the vulnerability mechanism itself, not just specific command patterns.
    """
    druid_host = os.getenv("DRUID_HOST", "localhost")
    druid_port = int(os.getenv("DRUID_PORT", "8888"))

    exploit_payloads = get_exploit_payloads()
    failed_exploits = []
    blocked_exploits = []

    try:
        import requests

        url = f"http://{druid_host}:{druid_port}/druid/indexer/v1/sampler"

        for payload_info in exploit_payloads:
            exploit_request = build_exploit_request(payload_info["js_function"])
            side_effect_path = payload_info.get("side_effect_path")
            if side_effect_path:
                Path(side_effect_path).unlink(missing_ok=True)

            try:
                response = requests.post(
                    url,
                    json=exploit_request,
                    headers={"Content-Type": "application/json"},
                    timeout=20
                )

                try:
                    _assert_explicit_exploit_rejection(response, payload_info)
                    if side_effect_path:
                        assert not Path(side_effect_path).exists(), (
                            f"Exploit {payload_info['name']} executed JavaScript and "
                            f"created its randomized side-effect marker"
                        )
                    blocked_exploits.append(payload_info["name"])
                except AssertionError as exc:
                    failed_exploits.append({
                        "name": payload_info["name"],
                        "reason": str(exc),
                    })

            except requests.exceptions.Timeout:
                failed_exploits.append({
                    "name": payload_info["name"],
                    "reason": "Request timed out - exploit may be executing"
                })

        # Report results
        print(f"\n✓ Blocked exploits ({len(blocked_exploits)}/{len(exploit_payloads)}):")
        for name in blocked_exploits:
            print(f"  - {name}")

        if failed_exploits:
            print(f"\n✗ FAILED exploits ({len(failed_exploits)}):")
            for f in failed_exploits:
                print(f"  - {f['name']}: {f['reason']}")

        assert len(failed_exploits) == 0, (
            f"CVE-2021-25646 fix incomplete! {len(failed_exploits)} exploits not blocked: "
            f"{[f['name'] for f in failed_exploits]}"
        )

        print(f"\n✓ All {len(exploit_payloads)} CVE-2021-25646 exploit variants blocked!")

    except requests.exceptions.ConnectionError:
        assert False, (
            f"Cannot connect to Druid server at {druid_host}:{druid_port}. "
            "The patched Druid must be built and running to verify the fix. "
            "Start Druid with: cd /root/druid && ./bin/start-single-server-small"
        )
