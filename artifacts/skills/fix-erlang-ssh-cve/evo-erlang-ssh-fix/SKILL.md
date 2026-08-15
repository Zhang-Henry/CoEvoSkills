---
name: evo-erlang-ssh-fix
description: "Fix CVE-2025-32433 in Erlang/OTP SSH server - unauthenticated connection message execution vulnerability. Use when tasked with fixing the SSH state machine vulnerability that allows pre-auth command execution."
---

# Erlang/OTP SSH Pre-Auth Connection Message Vulnerability Fix

## Problem

The Erlang/OTP SSH server's `ssh_connection_handler.erl` processes SSH connection
protocol messages (channel open, channel request, exec, etc.) via `{conn_msg, Msg}`
internal events WITHOUT checking whether the connection has reached the authenticated
`{connected, _}` state. An attacker can send crafted SSH connection protocol messages
before completing authentication, causing arbitrary command execution.

## Root Cause

In `ssh_connection_handler.erl`, the handler:
```erlang
handle_event(internal, {conn_msg,Msg}, StateName, #data{...} = D0) ->
```
does not guard on `?CONNECTED(StateName)`. All other capability-bearing handlers
(cast, call) properly use `when ?CONNECTED(StateName)` guards.

## Fix

Insert a guard clause BEFORE the existing `conn_msg` handler that disconnects
when connection messages arrive in a non-authenticated state:

```erlang
handle_event(internal, {conn_msg, _Msg}, StateName, _D) when not ?CONNECTED(StateName) ->
    ?DISCONNECT(?SSH_DISCONNECT_PROTOCOL_ERROR,
               "Connection message received before authentication was complete");
```

This preserves normal authenticated behavior while blocking pre-auth attacks.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-erlang-ssh-fix/scripts')
from utils import run_fix, validate_fix, find_ssh_connection_handler

# End-to-end: find, check, fix, and validate
result = run_fix('/app/workspace/otp_src_27.3.2')
assert result['success'], f"Fix failed: {result['message']}"

# Or validate an already-fixed file
fpath = find_ssh_connection_handler('/app/workspace/otp_src_27.3.2')
validation = validate_fix(fpath)
assert validation['valid'], f"Validation failed: {validation['checks']}"
```

## Key Functions

- `find_ssh_connection_handler(otp_src_dir)` - Locate the file in OTP source tree
- `check_vulnerability(filepath)` - Check if file is vulnerable
- `apply_fix(filepath)` - Apply the guard clause fix
- `validate_fix(filepath)` - Validate fix correctness (clause exists, ordering, etc.)
- `run_fix(otp_src_dir)` - End-to-end entry point
