import os
import re


def find_ssh_connection_handler(otp_src_dir):
    """Find the ssh_connection_handler.erl file in the OTP source tree."""
    target = os.path.join(otp_src_dir, "lib", "ssh", "src", "ssh_connection_handler.erl")
    if os.path.exists(target):
        return target
    for root, dirs, files in os.walk(otp_src_dir):
        if "ssh_connection_handler.erl" in files:
            return os.path.join(root, "ssh_connection_handler.erl")
    return None


def check_vulnerability(filepath):
    """Check if the ssh_connection_handler.erl file has the vulnerability."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    result = {
        'vulnerable': True,
        'has_guard': False,
        'conn_msg_line': None,
    }
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'conn_msg' in line and 'not ?CONNECTED' in line:
            result['has_guard'] = True
            result['vulnerable'] = False
        if re.search(r'handle_event\(internal,\s*\{conn_msg,\s*Msg\},\s*StateName,\s*#data\{', line):
            result['conn_msg_line'] = i + 1
    
    return result


def apply_fix(filepath):
    """Apply the fix to ssh_connection_handler.erl.
    
    Inserts a guard clause before the conn_msg handler that disconnects
    clients sending connection protocol messages before authentication.
    Uses ?DISCONNECT macro (throw-based) for clean disconnection.
    """
    status = check_vulnerability(filepath)
    if not status['vulnerable']:
        return {'success': True, 'message': 'File already has the fix applied.', 'already_fixed': True}
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    insert_idx = None
    for i, line in enumerate(lines):
        if re.search(r'handle_event\(internal,\s*\{conn_msg,\s*Msg\},\s*StateName,\s*#data\{', line):
            insert_idx = i
            break
    
    if insert_idx is None:
        return {'success': False, 'message': 'Could not find conn_msg handler to patch.', 'already_fixed': False}
    
    guard_clause = [
        'handle_event(internal, {conn_msg, _Msg}, StateName, _D) when not ?CONNECTED(StateName) ->\n',
        '    ?DISCONNECT(?SSH_DISCONNECT_PROTOCOL_ERROR,\n',
        '               "Connection message received before authentication was complete");\n',
    ]
    
    for j, guard_line in enumerate(guard_clause):
        lines.insert(insert_idx + j, guard_line)
    
    with open(filepath, 'w') as f:
        f.writelines(lines)
    
    verify = check_vulnerability(filepath)
    if not verify['vulnerable']:
        return {'success': True, 'message': 'Fix applied successfully.', 'already_fixed': False}
    else:
        return {'success': False, 'message': 'Fix applied but verification failed.', 'already_fixed': False}


def validate_fix(filepath):
    """Validate that the fix is correctly applied."""
    checks = []
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    has_guard = bool(re.search(
        r'handle_event\(internal,\s*\{conn_msg,\s*_Msg\},\s*StateName,\s*_D\)\s*when\s*not\s*\?CONNECTED\(StateName\)',
        content))
    checks.append(('guard_clause_exists', has_guard, 'Guard clause for conn_msg with not ?CONNECTED check'))
    
    has_disconnect = bool(re.search(r'DISCONNECT\(\?SSH_DISCONNECT_PROTOCOL_ERROR', content))
    checks.append(('disconnect_on_reject', has_disconnect, 'DISCONNECT with PROTOCOL_ERROR on unauthenticated conn_msg'))
    
    has_original = bool(re.search(
        r'handle_event\(internal,\s*\{conn_msg,\s*Msg\},\s*StateName,\s*#data\{', content))
    checks.append(('original_handler_preserved', has_original, 'Original conn_msg handler preserved'))
    
    guard_match = re.search(r'not \?CONNECTED\(StateName\)', content)
    original_match = re.search(r'handle_event\(internal,\s*\{conn_msg,\s*Msg\},\s*StateName,\s*#data\{', content)
    order_correct = guard_match and original_match and guard_match.start() < original_match.start()
    checks.append(('clause_ordering', order_correct, 'Guard clause before original handler'))
    
    all_valid = all(passed for _, passed, _ in checks)
    return {'valid': all_valid, 'checks': checks}


def run_fix(otp_src_dir):
    """End-to-end entry point."""
    filepath = find_ssh_connection_handler(otp_src_dir)
    if filepath is None:
        return {'success': False, 'message': 'ssh_connection_handler.erl not found'}
    
    print(f"Found: {filepath}")
    status = check_vulnerability(filepath)
    print(f"Vulnerability check: {'VULNERABLE' if status['vulnerable'] else 'ALREADY FIXED'}")
    
    fix_result = apply_fix(filepath)
    print(f"Fix result: {fix_result['message']}")
    
    if not fix_result['success']:
        return fix_result
    
    validation = validate_fix(filepath)
    print(f"Validation: {'PASSED' if validation['valid'] else 'FAILED'}")
    for check_name, passed, detail in validation['checks']:
        print(f"  {'[OK]' if passed else '[FAIL]'} {check_name}: {detail}")
    
    return {'success': validation['valid'], 'message': fix_result['message'], 'validation': validation}
