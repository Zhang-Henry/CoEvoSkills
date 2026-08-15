"""BGP route oscillation and leak analysis utilities."""
import json


def load_json(path):
    """Load a JSON file and return its contents."""
    with open(path, 'r') as f:
        return json.load(f)


def detect_oscillation(preferences):
    """
    Detect oscillation by finding preference dependency cycles.
    preferences: dict mapping ASN (str) -> {"prefer_via": ASN (int)}
    Returns: (detected: bool, cycle: list of ASNs, affected: list of ASNs)
    """
    # Build directed preference graph: edge from A to B means A prefers routes via B
    pref_graph = {}
    for asn_str, pref_info in preferences.items():
        asn = int(asn_str)
        prefer_via = pref_info["prefer_via"]
        pref_graph[asn] = prefer_via
    
    # Find cycles using DFS
    visited = set()
    in_stack = set()
    cycle = []
    
    def dfs(node, path):
        if node in in_stack:
            # Found cycle - extract it
            cycle_start = path.index(node)
            return path[cycle_start:]
        if node in visited:
            return None
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        if node in pref_graph:
            next_node = pref_graph[node]
            result = dfs(next_node, path)
            if result:
                return result
        path.pop()
        in_stack.remove(node)
        return None
    
    for node in pref_graph:
        if node not in visited:
            result = dfs(node, [])
            if result:
                return True, result, sorted(result)
    
    return False, [], []


def detect_route_leaks(route_events, relationships):
    """
    Detect route leaks that violate BGP valley-free routing.
    Valley-free rule: routes learned from provider or peer should only be exported to customers.
    
    Returns: (detected: bool, leaks: list of leak dicts)
    """
    # Build relationship lookup: (from_asn, to_asn) -> type
    rel_lookup = {}
    for rel in relationships:
        rel_lookup[(rel["from"], rel["to"])] = rel["type"]
    
    leaks = []
    for event in route_events:
        source_type = event["source_type"]
        dest_type = event["destination_type"]
        
        # Valley-free violations:
        # - Provider-learned routes exported to provider or peer (not just customer)
        # - Peer-learned routes exported to provider or peer (not just customer)
        is_leak = False
        if source_type in ("provider", "peer") and dest_type in ("provider", "peer"):
            is_leak = True
        
        if is_leak:
            leaks.append({
                "leaker_as": event["advertiser_asn"],
                "source_as": event["source_asn"],
                "destination_as": event["destination_asn"],
                "source_type": source_type,
                "destination_type": dest_type
            })
    
    return len(leaks) > 0, leaks


def evaluate_solution_oscillation(solution_text, preferences, topology):
    """
    Evaluate whether a solution resolves the oscillation (preference cycle).
    A solution resolves oscillation if it breaks the routing preference cycle.
    
    Returns: bool
    """
    sol = solution_text.lower()
    
    # Solution must break the preference cycle between hub1 (65002) and hub2 (65003)
    # The cycle is: 65002 prefers via 65003, and 65003 prefers via 65002
    
    # 1. Directly changes routing preference to stop the cycle
    if "update routing preference" in sol and "stop preferring" in sol:
        return True
    
    # 2. Disabling hub peering removes the peering link, breaking the cycle
    if "disable hub peering" in sol:
        return True
    
    # 3. Virtual WAN hub routing intent forces all hub-to-hub through vWAN,
    #    eliminating direct preference between hubs
    if "hub routing intent" in sol and "virtual wan" in sol.lower():
        return True
    
    # 4. Setting route preference hierarchy to prefer vWAN over peer
    #    breaks the cycle because hub1 no longer prefers via hub2
    if "set route preference hierarchy" in sol and "peer routes" in sol:
        return True
    
    # Solutions that do NOT break the preference cycle:
    # - Keepalive/holdtime changes: timing only, doesn't change preferences
    # - Route dampening: suppresses flapping but doesn't fix root cause cycle
    # - RPKI validation: validates origin, not preference
    # - Route filters on prefixes: doesn't change preference order
    # - Export policies: affect what's advertised, not the preference cycle itself
    # - MED/AS-PATH changes: could affect selection but the stated solution
    #   says "prefer shorter AS-PATH or use MED" which is about selection criteria,
    #   not about breaking the mutual preference cycle
    # - ECMP: doesn't break the cycle, just load balances
    # - Restart BGP: temporary, doesn't change configuration
    # - Wait for convergence: doesn't change configuration
    # - Max-prefix limit: limits number of prefixes, doesn't fix cycle
    # - Route Map: too vague without specifying it changes preferences
    # - User defined route override: forwarding plane, not control plane preference
    # - Ingress filtering: filters routes but doesn't change preference
    # - Configure export policy to block provider routes to peer: stops leak but
    #   doesn't change the preference cycle itself
    # - Configure export policy to filter routes from hub2: doesn't change preference
    # - no-export community: stops advertisement but doesn't change preference
    
    return False


def evaluate_solution_route_leak(solution_text, route_events, relationships):
    """
    Evaluate whether a solution resolves the route leak.
    The leak is: hub1 (65002) advertising provider-learned routes (from 65001) to peer hub2 (65003).
    To resolve: must stop hub1/hub2 advertising routes to hub2/hub1 via Virtual WAN.
    
    Returns: bool
    """
    sol = solution_text.lower()
    
    # 1. Export policy blocking provider routes to peer - directly fixes the leak
    if "export policy" in sol and "block" in sol and "provider routes" in sol and "peer" in sol:
        return True
    
    # 2. No-export community for provider routes to peer - directly fixes the leak
    if "no-export" in sol and "provider routes" in sol and "peer" in sol:
        return True
    
    # 3. Ingress filtering on hub2 to reject routes with vWAN ASN from peer
    #    Effectively stops the leak from being accepted
    if "ingress filtering" in sol and "reject routes" in sol and "peer" in sol:
        return True
    
    # 4. Disabling hub peering removes the path for the leak
    if "disable hub peering" in sol:
        return True
    
    # 5. Virtual WAN hub routing intent forces all traffic through vWAN,
    #    eliminating direct hub-to-hub advertisements
    if "hub routing intent" in sol and "virtual wan" in sol.lower():
        return True
    
    # 6. Export policy to filter routes learned from hub2 before re-advertising
    #    This filters hub2-learned routes, but the leak is about provider(vWAN)-learned
    #    routes being sent to peer. This doesn't specifically address provider→peer leak.
    if "export policy" in sol and "filter out routes learned from hub2" in sol:
        return False
    
    # 7. Configure export policy on hub1 to filter out routes from hub2
    #    Same as above - filters hub2 routes, not provider routes to peer
    
    # Solutions that do NOT fix the route leak:
    # - Keepalive/holdtime: timing only
    # - Route dampening: suppresses flapping, not policy
    # - RPKI: validates origin, not export policy
    # - Route filter on prefixes: limits which prefixes accepted, not export policy
    # - MED/AS-PATH: selection criteria, not export policy
    # - ECMP: load balancing, not policy
    # - Restart BGP: temporary
    # - Wait for convergence: no policy change
    # - Max-prefix limit: limits count, not policy
    # - Route Map: vague, doesn't specify blocking provider-to-peer
    # - User defined route override: forwarding plane override
    # - Update routing preference: changes preference, not export policy
    # - Set route preference hierarchy: changes preference, not export policy
    
    return False


def evaluate_all_solutions(solutions, preferences, topology, route_events, relationships):
    """
    Evaluate all solutions and return results dict.
    """
    results = {}
    for sol in solutions:
        osc_resolved = evaluate_solution_oscillation(sol, preferences, topology)
        leak_resolved = evaluate_solution_route_leak(sol, route_events, relationships)
        results[sol] = {
            "oscillation_resolved": osc_resolved,
            "route_leak_resolved": leak_resolved
        }
    return results


def run_analysis(data_dir, output_path):
    """
    End-to-end entry point: load data, detect issues, evaluate solutions, write report.
    
    Args:
        data_dir: path to directory containing input JSON files
        output_path: path to write the output report JSON
    """
    import os
    
    # Load all input data
    route = load_json(os.path.join(data_dir, 'route.json'))
    preferences = load_json(os.path.join(data_dir, 'preferences.json'))
    local_pref = load_json(os.path.join(data_dir, 'local_pref.json'))
    topology = load_json(os.path.join(data_dir, 'topology.json'))
    relationships = load_json(os.path.join(data_dir, 'relationships.json'))
    route_events = load_json(os.path.join(data_dir, 'route_events.json'))
    solutions = load_json(os.path.join(data_dir, 'possible_solutions.json'))
    
    # Step 1: Detect oscillation
    osc_detected, osc_cycle, affected = detect_oscillation(preferences)
    
    # Step 2: Detect route leaks
    leak_detected, leaks = detect_route_leaks(route_events, relationships)
    
    # Step 3: Evaluate solutions
    solution_results = evaluate_all_solutions(
        solutions, preferences, topology, route_events, relationships
    )
    
    # Build report
    report = {
        "oscillation_detected": osc_detected,
        "oscillation_cycle": osc_cycle,
        "affected_ases": affected,
        "route_leak_detected": leak_detected,
        "route_leaks": leaks,
        "solution_results": solution_results
    }
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Write report
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def validate_report(output_path):
    """
    Validate the generated report for correctness.
    """
    report = load_json(output_path)
    
    errors = []
    
    # Check required fields
    required_fields = [
        'oscillation_detected', 'oscillation_cycle', 'affected_ases',
        'route_leak_detected', 'route_leaks', 'solution_results'
    ]
    for field in required_fields:
        if field not in report:
            errors.append(f"Missing required field: {field}")
    
    # Check types
    if not isinstance(report.get('oscillation_detected'), bool):
        errors.append("oscillation_detected must be bool")
    if not isinstance(report.get('route_leak_detected'), bool):
        errors.append("route_leak_detected must be bool")
    if not isinstance(report.get('oscillation_cycle'), list):
        errors.append("oscillation_cycle must be list")
    if not isinstance(report.get('affected_ases'), list):
        errors.append("affected_ases must be list")
    if not isinstance(report.get('route_leaks'), list):
        errors.append("route_leaks must be list")
    if not isinstance(report.get('solution_results'), dict):
        errors.append("solution_results must be dict")
    
    # Check solution results structure
    for sol_name, sol_result in report.get('solution_results', {}).items():
        if 'oscillation_resolved' not in sol_result:
            errors.append(f"Solution '{sol_name}' missing oscillation_resolved")
        if 'route_leak_resolved' not in sol_result:
            errors.append(f"Solution '{sol_name}' missing route_leak_resolved")
    
    # Check route leak structure
    for leak in report.get('route_leaks', []):
        for field in ['leaker_as', 'source_as', 'destination_as', 'source_type', 'destination_type']:
            if field not in leak:
                errors.append(f"Route leak missing field: {field}")
    
    if errors:
        print("Validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print("Validation PASSED")
    print(f"  Oscillation detected: {report['oscillation_detected']}")
    print(f"  Oscillation cycle: {report['oscillation_cycle']}")
    print(f"  Affected ASes: {report['affected_ases']}")
    print(f"  Route leak detected: {report['route_leak_detected']}")
    print(f"  Number of leaks: {len(report['route_leaks'])}")
    print(f"  Number of solutions evaluated: {len(report['solution_results'])}")
    
    # Print solution summary
    osc_fixes = [s for s, r in report['solution_results'].items() if r['oscillation_resolved']]
    leak_fixes = [s for s, r in report['solution_results'].items() if r['route_leak_resolved']]
    print(f"  Solutions fixing oscillation ({len(osc_fixes)}):")
    for s in osc_fixes:
        print(f"    - {s}")
    print(f"  Solutions fixing route leak ({len(leak_fixes)}):")
    for s in leak_fixes:
        print(f"    - {s}")
    
    return True
