import json
import numpy as np
from pulp import *

def load_network(filepath):
    """Load MATPOWER network from JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    return data

def parse_network(data):
    """Parse MATPOWER data into structured arrays."""
    baseMVA = data['baseMVA']
    
    # Parse buses
    buses = []
    for b in data['bus']:
        buses.append({
            'id': int(b[0]),
            'type': int(b[1]),
            'Pd': b[2],  # MW
            'Qd': b[3],
        })
    
    # Parse generators
    gens = []
    for i, g in enumerate(data['gen']):
        gens.append({
            'idx': i,
            'bus': int(g[0]),
            'Pg': g[1],
            'Pmax': g[8],
            'Pmin': g[9],
            'status': int(g[7]),
        })
    
    # Parse branches
    branches = []
    for i, br in enumerate(data['branch']):
        branches.append({
            'idx': i,
            'from': int(br[0]),
            'to': int(br[1]),
            'r': br[2],
            'x': br[3],
            'rateA': br[5],  # MW thermal limit
            'status': int(br[10]),
        })
    
    # Parse gencost - polynomial model type 2 with 3 coefficients
    # cost = c2*p^2 + c1*p + c0
    gencosts = []
    for gc in data['gencost']:
        ncost = int(gc[3])
        coeffs = gc[4:4+ncost]
        gencosts.append({
            'c2': coeffs[0] if len(coeffs) >= 3 else 0.0,
            'c1': coeffs[1] if len(coeffs) >= 2 else 0.0,
            'c0': coeffs[2] if len(coeffs) >= 1 else 0.0,
        })
    
    # Reserve data
    reserve_cap = data['reserve_capacity']
    reserve_req = data['reserve_requirement']
    
    return baseMVA, buses, gens, branches, gencosts, reserve_cap, reserve_req

def solve_dcopf(data, branch_overrides=None):
    """
    Solve DC-OPF with reserve co-optimization.
    
    branch_overrides: dict mapping branch index to new rateA value
    
    Returns dict with total_cost, lmps, reserve_mcp, binding_lines, gen_dispatch
    """
    baseMVA, buses, gens, branches, gencosts, reserve_cap, reserve_req = parse_network(data)
    
    if branch_overrides is None:
        branch_overrides = {}
    
    # Apply branch overrides
    for idx, new_rate in branch_overrides.items():
        branches[idx]['rateA'] = new_rate
    
    # Build bus index mapping
    bus_ids = sorted(set(b['id'] for b in buses))
    bus_idx = {bid: i for i, bid in enumerate(bus_ids)}
    n_bus = len(bus_ids)
    
    # Find slack/reference bus
    ref_bus = None
    for b in buses:
        if b['type'] == 3:
            ref_bus = b['id']
            break
    if ref_bus is None:
        ref_bus = bus_ids[0]
    
    # Filter active generators and branches
    active_gens = [g for g in gens if g['status'] == 1]
    active_branches = [br for br in branches if br['status'] == 1]
    
    n_gen = len(active_gens)
    n_branch = len(active_branches)
    
    # Create LP problem
    prob = LpProblem("DCOPF_Reserve", LpMinimize)
    
    # Decision variables
    # Generator power output
    pg = {}
    for g in active_gens:
        pg[g['idx']] = LpVariable(f"pg_{g['idx']}", 
                                   lowBound=g['Pmin'],
                                   upBound=g['Pmax'])
    
    # Reserve variables
    rv = {}
    for g in active_gens:
        rcap = reserve_cap[g['idx']]
        rv[g['idx']] = LpVariable(f"rv_{g['idx']}",
                                   lowBound=0,
                                   upBound=rcap)
    
    # Bus voltage angles (in radians)
    theta = {}
    for bid in bus_ids:
        theta[bid] = LpVariable(f"theta_{bid}",
                                 lowBound=-np.pi,
                                 upBound=np.pi)
    
    # Fix reference bus angle
    prob += theta[ref_bus] == 0, "ref_angle"
    
    # Objective: minimize total generation cost
    # Since c2=0 for all, cost is linear: c1 * pg
    # Note: reserve has no explicit cost in standard formulation
    # (its cost is implicit through capacity coupling)
    obj = lpSum(gencosts[g['idx']]['c1'] * pg[g['idx']] + 
                gencosts[g['idx']]['c0'] 
                for g in active_gens)
    prob += obj
    
    # Power balance constraints at each bus
    # sum(pg at bus) - Pd = sum(flow out) - sum(flow in)
    # Flow on branch: f = (theta_from - theta_to) / x  (in MW, with baseMVA)
    
    # Build flow expressions for each branch
    flow = {}
    for br in active_branches:
        x = br['x']
        if x == 0:
            x = 1e-6  # avoid division by zero
        # Flow in MW: baseMVA * (theta_from - theta_to) / x
        flow[br['idx']] = baseMVA * (theta[br['from']] - theta[br['to']]) / x
    
    # Bus injection = sum of gen at bus - demand at bus
    bus_demand = {bid: 0.0 for bid in bus_ids}
    for b in buses:
        bus_demand[b['id']] = b['Pd']
    
    bus_gen = {bid: [] for bid in bus_ids}
    for g in active_gens:
        bus_gen[g['bus']].append(g['idx'])
    
    # Branches connected to each bus
    bus_branches_from = {bid: [] for bid in bus_ids}
    bus_branches_to = {bid: [] for bid in bus_ids}
    for br in active_branches:
        bus_branches_from[br['from']].append(br['idx'])
        bus_branches_to[br['to']].append(br['idx'])
    
    # Power balance: gen - demand = net flow out
    balance_constraints = {}
    for bid in bus_ids:
        gen_sum = lpSum(pg[gidx] for gidx in bus_gen[bid]) if bus_gen[bid] else 0
        flow_out = lpSum(flow[bridx] for bridx in bus_branches_from[bid]) if bus_branches_from[bid] else 0
        flow_in = lpSum(flow[bridx] for bridx in bus_branches_to[bid]) if bus_branches_to[bid] else 0
        
        cname = f"balance_{bid}"
        constraint = gen_sum - bus_demand[bid] == flow_out - flow_in
        prob += constraint, cname
        balance_constraints[bid] = cname
    
    # Branch flow limits
    flow_limit_constraints = {}
    for br in active_branches:
        rate = br['rateA']
        if rate > 0:  # 0 means unlimited
            cname_upper = f"flow_upper_{br['idx']}"
            cname_lower = f"flow_lower_{br['idx']}"
            prob += flow[br['idx']] <= rate, cname_upper
            prob += flow[br['idx']] >= -rate, cname_lower
            flow_limit_constraints[br['idx']] = (cname_upper, cname_lower)
    
    # Capacity coupling: pg + rv <= Pmax
    for g in active_gens:
        prob += pg[g['idx']] + rv[g['idx']] <= g['Pmax'], f"cap_coupling_{g['idx']}"
    
    # System reserve requirement: sum(rv) >= reserve_req
    prob += lpSum(rv[g['idx']] for g in active_gens) >= reserve_req, "reserve_req"
    
    # Solve
    solver = PULP_CBC_CMD(msg=0, timeLimit=300)
    status = prob.solve(solver)
    
    if LpStatus[status] != 'Optimal':
        print(f"WARNING: Solver status = {LpStatus[status]}")
        return None
    
    # Extract results
    total_cost = value(prob.objective)
    
    # LMPs from dual values of power balance constraints
    lmps = {}
    for bid in bus_ids:
        cname = balance_constraints[bid]
        con = prob.constraints[cname]
        # The dual value (shadow price) gives the LMP
        # For minimization with == constraint, dual is the marginal price
        lmp = con.pi if con.pi is not None else 0.0
        lmps[bid] = lmp
    
    # Reserve MCP from dual of reserve requirement constraint
    reserve_con = prob.constraints["reserve_req"]
    reserve_mcp = reserve_con.pi if reserve_con.pi is not None else 0.0
    # Reserve requirement is >= constraint, so dual should be non-negative
    # In PuLP, for >= constraint rewritten as -sum <= -req, dual sign may flip
    reserve_mcp = abs(reserve_mcp)
    
    # Binding lines (loading >= 99%)
    binding_lines = []
    for br in active_branches:
        rate = br['rateA']
        if rate > 0:
            flow_val = value(flow[br['idx']])
            if flow_val is None:
                continue
            loading = abs(flow_val) / rate
            if loading >= 0.99:
                binding_lines.append({
                    'from': br['from'],
                    'to': br['to'],
                    'flow_MW': round(abs(flow_val), 6),
                    'limit_MW': round(rate, 6)
                })
    
    # Generator dispatch
    gen_dispatch = {}
    for g in active_gens:
        gen_dispatch[g['idx']] = {
            'pg': value(pg[g['idx']]),
            'rv': value(rv[g['idx']]),
            'bus': g['bus']
        }
    
    return {
        'total_cost': total_cost,
        'lmps': lmps,
        'reserve_mcp': reserve_mcp,
        'binding_lines': binding_lines,
        'gen_dispatch': gen_dispatch,
        'status': LpStatus[status]
    }

def find_branch_index(data, from_bus, to_bus):
    """Find the index of a branch connecting two buses."""
    for i, br in enumerate(data['branch']):
        if (int(br[0]) == from_bus and int(br[1]) == to_bus) or \
           (int(br[0]) == to_bus and int(br[1]) == from_bus):
            return i
    return None

def get_branch_rate(data, branch_idx):
    """Get the RATE_A of a branch."""
    return data['branch'][branch_idx][5]

def run_analysis(network_path, output_path, from_bus=64, to_bus=1501, capacity_increase=0.20):
    """
    Run base case and counterfactual DC-OPF analysis.
    
    Args:
        network_path: path to network.json
        output_path: path to write report.json
        from_bus: from bus of the line to modify
        to_bus: to bus of the line to modify  
        capacity_increase: fractional increase (0.20 = 20%)
    """
    data = load_network(network_path)
    
    # Find the target branch
    br_idx = find_branch_index(data, from_bus, to_bus)
    if br_idx is None:
        raise ValueError(f"Branch {from_bus}-{to_bus} not found")
    
    base_rate = get_branch_rate(data, br_idx)
    new_rate = base_rate * (1 + capacity_increase)
    
    print(f"Target branch index: {br_idx}")
    print(f"Base rate: {base_rate} MW, New rate: {new_rate} MW")
    
    # Solve base case
    print("\nSolving base case...")
    base_result = solve_dcopf(data)
    if base_result is None:
        raise RuntimeError("Base case failed to solve")
    print(f"Base case total cost: {base_result['total_cost']:.2f}")
    print(f"Base case binding lines: {len(base_result['binding_lines'])}")
    
    # Solve counterfactual
    print("\nSolving counterfactual...")
    cf_result = solve_dcopf(data, branch_overrides={br_idx: new_rate})
    if cf_result is None:
        raise RuntimeError("Counterfactual failed to solve")
    print(f"Counterfactual total cost: {cf_result['total_cost']:.2f}")
    print(f"Counterfactual binding lines: {len(cf_result['binding_lines'])}")
    
    # Build report
    report = build_report(base_result, cf_result, from_bus, to_bus, data)
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nReport written to {output_path}")
    return report

def build_report(base_result, cf_result, from_bus, to_bus, data):
    """Build the report.json structure."""
    bus_ids = sorted(set(int(b[0]) for b in data['bus']))
    
    # LMP by bus for base case
    base_lmps = []
    for bid in bus_ids:
        base_lmps.append({
            'bus': bid,
            'lmp_dollars_per_MWh': round(base_result['lmps'].get(bid, 0.0), 6)
        })
    
    # LMP by bus for counterfactual
    cf_lmps = []
    for bid in bus_ids:
        cf_lmps.append({
            'bus': bid,
            'lmp_dollars_per_MWh': round(cf_result['lmps'].get(bid, 0.0), 6)
        })
    
    # Cost reduction
    cost_reduction = base_result['total_cost'] - cf_result['total_cost']
    
    # Buses with largest LMP drop
    lmp_drops = []
    for bid in bus_ids:
        base_lmp = base_result['lmps'].get(bid, 0.0)
        cf_lmp = cf_result['lmps'].get(bid, 0.0)
        delta = cf_lmp - base_lmp
        lmp_drops.append({
            'bus': bid,
            'base_lmp': round(base_lmp, 6),
            'cf_lmp': round(cf_lmp, 6),
            'delta': round(delta, 6)
        })
    
    # Sort by delta (most negative first = largest drop)
    lmp_drops.sort(key=lambda x: x['delta'])
    top3 = lmp_drops[:3]
    
    # Check if the target line is binding in counterfactual
    target_binding_in_cf = False
    for bl in cf_result['binding_lines']:
        if (bl['from'] == from_bus and bl['to'] == to_bus) or \
           (bl['from'] == to_bus and bl['to'] == from_bus):
            target_binding_in_cf = True
            break
    
    # congestion_relieved = True means NOT binding in counterfactual
    congestion_relieved = not target_binding_in_cf
    
    report = {
        'base_case': {
            'total_cost_dollars_per_hour': round(base_result['total_cost'], 6),
            'lmp_by_bus': base_lmps,
            'reserve_mcp_dollars_per_MWh': round(base_result['reserve_mcp'], 6),
            'binding_lines': base_result['binding_lines']
        },
        'counterfactual': {
            'total_cost_dollars_per_hour': round(cf_result['total_cost'], 6),
            'lmp_by_bus': cf_lmps,
            'reserve_mcp_dollars_per_MWh': round(cf_result['reserve_mcp'], 6),
            'binding_lines': cf_result['binding_lines']
        },
        'impact_analysis': {
            'cost_reduction_dollars_per_hour': round(cost_reduction, 6),
            'buses_with_largest_lmp_drop': top3,
            'congestion_relieved': congestion_relieved
        }
    }
    
    return report

def validate_report(report_path):
    """Validate the report.json structure and values."""
    with open(report_path) as f:
        report = json.load(f)
    
    errors = []
    
    # Check required keys
    for key in ['base_case', 'counterfactual', 'impact_analysis']:
        if key not in report:
            errors.append(f"Missing key: {key}")
    
    for case in ['base_case', 'counterfactual']:
        if case in report:
            for field in ['total_cost_dollars_per_hour', 'lmp_by_bus', 
                         'reserve_mcp_dollars_per_MWh', 'binding_lines']:
                if field not in report[case]:
                    errors.append(f"Missing {case}.{field}")
    
    if 'impact_analysis' in report:
        for field in ['cost_reduction_dollars_per_hour', 
                      'buses_with_largest_lmp_drop', 'congestion_relieved']:
            if field not in report['impact_analysis']:
                errors.append(f"Missing impact_analysis.{field}")
        
        # Check top 3 buses
        top3 = report['impact_analysis'].get('buses_with_largest_lmp_drop', [])
        if len(top3) != 3:
            errors.append(f"Expected 3 buses in largest_lmp_drop, got {len(top3)}")
    
    # Verify cost reduction consistency
    if 'base_case' in report and 'counterfactual' in report:
        base_cost = report['base_case']['total_cost_dollars_per_hour']
        cf_cost = report['counterfactual']['total_cost_dollars_per_hour']
        expected_reduction = base_cost - cf_cost
        actual_reduction = report['impact_analysis']['cost_reduction_dollars_per_hour']
        if abs(expected_reduction - actual_reduction) > 0.01:
            errors.append(f"Cost reduction mismatch: {expected_reduction} vs {actual_reduction}")
    
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("Validation passed!")
        return True
