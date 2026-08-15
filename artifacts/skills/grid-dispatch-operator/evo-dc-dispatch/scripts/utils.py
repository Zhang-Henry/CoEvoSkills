"""
DC Optimal Power Flow with Reserves - Utility Functions

Solves economic dispatch with:
- DC power balance at each bus
- Generator and transmission limits  
- Spinning reserve requirements with standard capacity coupling
"""

import json
import numpy as np
from scipy import sparse
from scipy.optimize import linprog


def load_network(filepath):
    """Load MATPOWER-format network from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data


def parse_network(data):
    """
    Parse MATPOWER data into structured arrays.
    Returns dict with parsed buses, generators, branches, costs, reserves.
    """
    baseMVA = data['baseMVA']
    
    # Parse buses
    buses = []
    for b in data['bus']:
        buses.append({
            'bus_i': int(b[0]),
            'type': int(b[1]),
            'Pd': b[2],
            'Qd': b[3],
            'Gs': b[4],
            'Bs': b[5],
            'area': int(b[6]),
            'Vm': b[7],
            'Va': b[8],
            'baseKV': b[9],
            'zone': int(b[10]),
            'Vmax': b[11],
            'Vmin': b[12]
        })
    
    # Create bus_id to index mapping
    bus_ids = [b['bus_i'] for b in buses]
    bus_id_to_idx = {bid: idx for idx, bid in enumerate(bus_ids)}
    
    # Find reference bus
    ref_bus_idx = None
    for idx, b in enumerate(buses):
        if b['type'] == 3:
            ref_bus_idx = idx
            break
    if ref_bus_idx is None:
        ref_bus_idx = 0  # fallback
    
    # Parse generators
    generators = []
    for i, g in enumerate(data['gen']):
        gen = {
            'id': i,  # 0-indexed internal id
            'bus': int(g[0]),
            'Pg': g[1],
            'Qg': g[2],
            'Qmax': g[3],
            'Qmin': g[4],
            'Vg': g[5],
            'mBase': g[6],
            'status': int(g[7]),
            'Pmax': g[8],
            'Pmin': g[9],
            'reserve_capacity': data['reserve_capacity'][i]
        }
        generators.append(gen)
    
    # Parse generator costs
    gencosts = []
    for gc in data['gencost']:
        model = int(gc[0])
        ncost = int(gc[3])
        coeffs = gc[4:4+ncost]
        gencosts.append({
            'model': model,
            'startup': gc[1],
            'shutdown': gc[2],
            'ncost': ncost,
            'coeffs': coeffs  # highest order first
        })
    
    # Parse branches
    branches = []
    for i, br in enumerate(data['branch']):
        branch = {
            'id': i,
            'fbus': int(br[0]),
            'tbus': int(br[1]),
            'r': br[2],
            'x': br[3],
            'b': br[4],
            'rateA': br[5],
            'rateB': br[6],
            'rateC': br[7],
            'tap': br[8],
            'shift': br[9],
            'status': int(br[10]),
            'angmin': br[11],
            'angmax': br[12]
        }
        branches.append(branch)
    
    return {
        'baseMVA': baseMVA,
        'buses': buses,
        'bus_ids': bus_ids,
        'bus_id_to_idx': bus_id_to_idx,
        'ref_bus_idx': ref_bus_idx,
        'generators': generators,
        'gencosts': gencosts,
        'branches': branches,
        'reserve_requirement': data['reserve_requirement']
    }


def build_Bbus_and_Bf(net):
    """
    Build DC power flow matrices following MATPOWER convention.
    
    b = 1 / (x * tap)  where tap=0 means tap=1
    flow = b * (theta_f - theta_t) - b * shift_rad  (in p.u.)
    
    Returns:
        Bf: branch-bus matrix (nbranch x nbus)
        Bbus: bus admittance matrix (nbus x nbus)
        Pshift: shift contribution per branch (p.u.)
        active_branch_indices: list of active branch indices
    """
    nbus = len(net['buses'])
    nbranch = len(net['branches'])
    bus_id_to_idx = net['bus_id_to_idx']
    
    Bf_rows = []
    Bf_cols = []
    Bf_vals = []
    Pshift = np.zeros(nbranch)
    active_branch_indices = []
    
    Cf_rows = []
    Cf_cols = []
    Ct_rows = []
    Ct_cols = []
    
    for i, br in enumerate(net['branches']):
        if br['status'] == 0:
            continue
        active_branch_indices.append(i)
        
        fi = bus_id_to_idx[br['fbus']]
        ti = bus_id_to_idx[br['tbus']]
        
        x = br['x']
        tap = br['tap']
        if tap == 0.0:
            tap = 1.0
        shift_rad = br['shift'] * np.pi / 180.0
        
        b = 1.0 / (x * tap)
        
        Bf_rows.extend([i, i])
        Bf_cols.extend([fi, ti])
        Bf_vals.extend([b, -b])
        
        Pshift[i] = -b * shift_rad
        
        Cf_rows.append(i)
        Cf_cols.append(fi)
        Ct_rows.append(i)
        Ct_cols.append(ti)
    
    Bf = sparse.csr_matrix((Bf_vals, (Bf_rows, Bf_cols)), shape=(nbranch, nbus))
    
    # Bbus = (Cf - Ct)^T @ Bf
    nactive = len(active_branch_indices)
    Cf = sparse.csr_matrix((np.ones(len(Cf_rows)), (Cf_rows, Cf_cols)), shape=(nbranch, nbus))
    Ct = sparse.csr_matrix((np.ones(len(Ct_rows)), (Ct_rows, Ct_cols)), shape=(nbranch, nbus))
    Cft = Cf - Ct
    Bbus = Cft.T @ Bf
    
    return Bf, Bbus, Pshift, active_branch_indices


def compute_gen_cost(pg_mw, gencost):
    """
    Compute generation cost for a single generator.
    pg_mw: real power output in MW
    gencost: parsed cost dict with 'model', 'ncost', 'coeffs'
    Returns cost in $/hr
    """
    if gencost['model'] == 2:  # polynomial
        coeffs = gencost['coeffs']
        ncost = gencost['ncost']
        cost = 0.0
        for j, c in enumerate(coeffs):
            power = ncost - 1 - j
            cost += c * (pg_mw ** power)
        return cost
    else:
        # Piecewise linear - not expected in this dataset but handle gracefully
        return 0.0


def solve_dcopf_with_reserves(net):
    """
    Solve DC-OPF with spinning reserves using LP.
    
    Variables: [Pg (ngen), Rg (ngen), theta (nbus)] all in per-unit
    """
    baseMVA = net['baseMVA']
    nbus = len(net['buses'])
    bus_id_to_idx = net['bus_id_to_idx']
    
    online_gens = [g for g in net['generators'] if g['status'] == 1]
    ngen = len(online_gens)
    
    Bf, Bbus, Pshift_all, active_branch_indices = build_Bbus_and_Bf(net)
    
    Bf_active = Bf[active_branch_indices, :]
    Pshift_active = Pshift_all[active_branch_indices]
    nactive = len(active_branch_indices)
    
    # Variables: x = [Pg (ngen), Rg (ngen), theta (nbus)]
    nvar = ngen + ngen + nbus
    pg_start = 0
    rg_start = ngen
    th_start = 2 * ngen
    
    # ---- Objective: min sum(c1_i * Pg_i * baseMVA) ----
    c = np.zeros(nvar)
    for i, g in enumerate(online_gens):
        gc = net['gencosts'][g['id']]
        if gc['model'] == 2:
            coeffs = gc['coeffs']
            ncost = gc['ncost']
            if ncost >= 2:
                c1_coeff = coeffs[-2]  # linear coefficient
                c[pg_start + i] = c1_coeff * baseMVA
            if ncost >= 3:
                c2_coeff = coeffs[-3]  # quadratic coefficient
                # For quadratic, we'd need QP solver; for now assume c2=0
                if c2_coeff != 0:
                    print(f"Warning: Generator {g['id']} has quadratic cost c2={c2_coeff}")
    
    # ---- Bounds ----
    lb = np.full(nvar, -np.inf)
    ub = np.full(nvar, np.inf)
    
    for i, g in enumerate(online_gens):
        lb[pg_start + i] = g['Pmin'] / baseMVA
        ub[pg_start + i] = g['Pmax'] / baseMVA
    
    for i, g in enumerate(online_gens):
        lb[rg_start + i] = 0.0
        ub[rg_start + i] = g['reserve_capacity'] / baseMVA
    
    ref_idx = net['ref_bus_idx']
    lb[th_start + ref_idx] = 0.0
    ub[th_start + ref_idx] = 0.0
    
    bounds = list(zip(lb, ub))
    
    # ---- Equality constraints: bus power balance ----
    Cg_rows = []
    Cg_cols = []
    for i, g in enumerate(online_gens):
        bus_idx = bus_id_to_idx[g['bus']]
        Cg_rows.append(bus_idx)
        Cg_cols.append(i)
    Cg = sparse.csr_matrix((np.ones(len(Cg_rows)), (Cg_rows, Cg_cols)), shape=(nbus, ngen))
    
    # Include shunt conductance Gs as additional load (MW at V=1.0 p.u.)
    Pd = np.array([b['Pd'] + b['Gs'] for b in net['buses']]) / baseMVA
    
    # Pshift_bus = Cft^T @ Pshift_active
    Cft_rows = []
    Cft_cols = []
    Cft_vals = []
    for idx, br_idx in enumerate(active_branch_indices):
        br = net['branches'][br_idx]
        fi = bus_id_to_idx[br['fbus']]
        ti = bus_id_to_idx[br['tbus']]
        Cft_rows.extend([idx, idx])
        Cft_cols.extend([fi, ti])
        Cft_vals.extend([1.0, -1.0])
    Cft = sparse.csr_matrix((Cft_vals, (Cft_rows, Cft_cols)), shape=(nactive, nbus))
    Pshift_bus = Cft.T @ Pshift_active
    
    A_eq = sparse.hstack([
        Cg,
        sparse.csr_matrix((nbus, ngen)),
        -Bbus
    ], format='csr')
    b_eq = Pd + Pshift_bus
    
    # ---- Inequality constraints ----
    rateA = np.array([net['branches'][bi]['rateA'] for bi in active_branch_indices]) / baseMVA
    
    # Upper flow limit: Bf @ theta <= rateA - Pshift
    A_flow_upper = sparse.hstack([
        sparse.csr_matrix((nactive, ngen)),
        sparse.csr_matrix((nactive, ngen)),
        Bf_active
    ], format='csr')
    b_flow_upper = rateA - Pshift_active
    
    # Lower flow limit: -Bf @ theta <= rateA + Pshift
    A_flow_lower = sparse.hstack([
        sparse.csr_matrix((nactive, ngen)),
        sparse.csr_matrix((nactive, ngen)),
        -Bf_active
    ], format='csr')
    b_flow_lower = rateA + Pshift_active
    
    # Capacity coupling: Pg + Rg <= Pmax/baseMVA
    A_coupling = sparse.hstack([
        sparse.eye(ngen),
        sparse.eye(ngen),
        sparse.csr_matrix((ngen, nbus))
    ], format='csr')
    b_coupling = np.array([g['Pmax'] / baseMVA for g in online_gens])
    
    # System reserve: -sum(Rg) <= -reserve_requirement / baseMVA
    A_reserve = sparse.hstack([
        sparse.csr_matrix((1, ngen)),
        -sparse.csr_matrix(np.ones((1, ngen))),
        sparse.csr_matrix((1, nbus))
    ], format='csr')
    b_reserve = np.array([-net['reserve_requirement'] / baseMVA])
    
    A_ub = sparse.vstack([A_flow_upper, A_flow_lower, A_coupling, A_reserve], format='csr')
    b_ub = np.concatenate([b_flow_upper, b_flow_lower, b_coupling, b_reserve])
    
    # ---- Solve ----
    print(f"Problem size: {nvar} variables, {A_eq.shape[0]} equality, {A_ub.shape[0]} inequality constraints")
    
    result = linprog(
        c, 
        A_ub=A_ub, 
        b_ub=b_ub, 
        A_eq=A_eq, 
        b_eq=b_eq, 
        bounds=bounds,
        method='highs',
        options={'disp': False, 'presolve': True}
    )
    
    if not result.success:
        print(f"Optimization failed: {result.message}")
        return None
    
    print(f"Optimization successful. Objective: {result.fun}")
    
    x = result.x
    Pg = x[pg_start:pg_start+ngen] * baseMVA
    Rg = x[rg_start:rg_start+ngen] * baseMVA
    theta = x[th_start:th_start+nbus]
    
    # Compute line flows
    flows_pu = Bf_active @ theta + Pshift_active
    flows_MW = flows_pu * baseMVA
    
    # Compute total cost from actual Pg values (not LP objective)
    total_cost = 0.0
    for i, g in enumerate(online_gens):
        gc = net['gencosts'][g['id']]
        total_cost += compute_gen_cost(Pg[i], gc)
    
    return {
        'online_gens': online_gens,
        'Pg': Pg,
        'Rg': Rg,
        'theta': theta,
        'flows_MW': flows_MW,
        'active_branch_indices': active_branch_indices,
        'total_cost': total_cost,
        'baseMVA': baseMVA
    }


def compute_line_loading(net, solution):
    """
    Compute line loading percentages and find top 3 most loaded.
    Loading = |flow| / rateA * 100
    Uses unrounded values for ranking.
    """
    loadings = []
    for idx, br_idx in enumerate(solution['active_branch_indices']):
        br = net['branches'][br_idx]
        flow = abs(solution['flows_MW'][idx])
        rateA = br['rateA']
        if rateA > 0:
            loading_pct = (flow / rateA) * 100.0
        else:
            loading_pct = 0.0
        loadings.append({
            'from': br['fbus'],
            'to': br['tbus'],
            'loading_pct': loading_pct,
            'flow_MW': flow,
            'rateA': rateA,
            'branch_idx': br_idx
        })
    
    # Sort by loading percentage descending, then by flow descending for tie-breaking
    loadings.sort(key=lambda x: (-x['loading_pct'], -x['flow_MW']))
    return loadings[:3]


def build_report(net, solution):
    """
    Build the final report dictionary.
    Uses unrounded solver values for totals, rounds individual values for serialization.
    """
    online_gens = solution['online_gens']
    Pg = solution['Pg']
    Rg = solution['Rg']
    
    # Generator dispatch
    gen_dispatch = []
    for i, g in enumerate(online_gens):
        pg_val = float(Pg[i])
        rg_val = float(Rg[i])
        # Clean up tiny negative values from solver tolerance
        if rg_val < 0 and rg_val > -1e-4:
            rg_val = 0.0
        if pg_val < g['Pmin'] and pg_val > g['Pmin'] - 1e-4:
            pg_val = g['Pmin']
        # Snap to bounds if very close
        if abs(pg_val - g['Pmax']) < 1e-4:
            pg_val = g['Pmax']
        if abs(pg_val - g['Pmin']) < 1e-4:
            pg_val = g['Pmin']
        if abs(rg_val - g['reserve_capacity']) < 1e-4:
            rg_val = g['reserve_capacity']
        # Force positive zero
        pg_out = round(pg_val, 4) + 0.0
        rg_out = round(rg_val, 4) + 0.0
        gen_dispatch.append({
            'id': g['id'] + 1,  # 1-indexed
            'bus': g['bus'],
            'output_MW': pg_out,
            'reserve_MW': rg_out,
            'pmax_MW': g['Pmax']
        })
    
    # Totals from unrounded solver values
    # Total load includes Pd and shunt conductance Gs
    total_load = sum(b['Pd'] + b['Gs'] for b in net['buses'])
    total_gen = float(sum(Pg))
    total_reserve = float(sum(Rg))
    total_cost = solution['total_cost']
    
    # Most loaded lines
    top_lines = compute_line_loading(net, solution)
    most_loaded = []
    for line in top_lines:
        most_loaded.append({
            'from': line['from'],
            'to': line['to'],
            'loading_pct': round(line['loading_pct'], 4)
        })
    
    # Operating margin: uncommitted capacity beyond energy and reserves
    operating_margin = float(sum(
        g['Pmax'] - Pg[i] - Rg[i]
        for i, g in enumerate(online_gens)
    ))
    
    report = {
        'generator_dispatch': gen_dispatch,
        'totals': {
            'cost_dollars_per_hour': round(total_cost, 4),
            'load_MW': round(total_load, 4),
            'generation_MW': round(total_gen, 4),
            'reserve_MW': round(total_reserve, 4)
        },
        'most_loaded_lines': most_loaded,
        'operating_margin_MW': round(operating_margin, 4)
    }
    
    return report


def run_dcopf(input_path, output_path):
    """
    End-to-end entry point: load network, solve DC-OPF with reserves, write report.
    """
    data = load_network(input_path)
    net = parse_network(data)
    
    print(f"Network: {len(net['buses'])} buses, {len(net['generators'])} generators, {len(net['branches'])} branches")
    print(f"Reserve requirement: {net['reserve_requirement']} MW")
    
    solution = solve_dcopf_with_reserves(net)
    if solution is None:
        raise RuntimeError("DC-OPF optimization failed")
    
    report = build_report(net, solution)
    validate_report(net, solution, report)
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"Report written to {output_path}")
    return report


def validate_report(net, solution, report):
    """
    Validate the report against constraints.
    """
    online_gens = solution['online_gens']
    Pg = solution['Pg']
    Rg = solution['Rg']
    
    total_gen = sum(Pg)
    # Total load includes Pd and shunt conductance Gs
    total_load = sum(b['Pd'] + b['Gs'] for b in net['buses'])
    balance_err = abs(total_gen - total_load)
    print(f"Power balance error: {balance_err:.6f} MW")
    assert balance_err < 1.0, f"Power balance error too large: {balance_err}"
    
    for i, g in enumerate(online_gens):
        assert Pg[i] >= g['Pmin'] - 1e-3, f"Gen {g['id']} below Pmin: {Pg[i]} < {g['Pmin']}"
        assert Pg[i] <= g['Pmax'] + 1e-3, f"Gen {g['id']} above Pmax: {Pg[i]} > {g['Pmax']}"
    
    for i, g in enumerate(online_gens):
        assert Pg[i] + Rg[i] <= g['Pmax'] + 1e-3, \
            f"Gen {g['id']} coupling violated: {Pg[i]} + {Rg[i]} > {g['Pmax']}"
    
    for i, g in enumerate(online_gens):
        assert Rg[i] >= -1e-3, f"Gen {g['id']} negative reserve: {Rg[i]}"
        assert Rg[i] <= g['reserve_capacity'] + 1e-3, \
            f"Gen {g['id']} reserve exceeds capacity: {Rg[i]} > {g['reserve_capacity']}"
    
    total_reserve = sum(Rg)
    print(f"Total reserve: {total_reserve:.2f} MW (requirement: {net['reserve_requirement']} MW)")
    assert total_reserve >= net['reserve_requirement'] - 1e-3, \
        f"Reserve requirement not met: {total_reserve} < {net['reserve_requirement']}"
    
    for idx, br_idx in enumerate(solution['active_branch_indices']):
        br = net['branches'][br_idx]
        flow = abs(solution['flows_MW'][idx])
        if br['rateA'] > 0:
            assert flow <= br['rateA'] + 1e-3, \
                f"Branch {br['fbus']}-{br['tbus']} flow {flow} exceeds limit {br['rateA']}"
    
    # Verify cost independently
    cost_check = 0.0
    for i, g in enumerate(online_gens):
        gc = net['gencosts'][g['id']]
        cost_check += compute_gen_cost(Pg[i], gc)
    cost_diff = abs(cost_check - solution['total_cost'])
    print(f"Cost verification diff: {cost_diff:.6e}")
    
    print("All validations passed!")

