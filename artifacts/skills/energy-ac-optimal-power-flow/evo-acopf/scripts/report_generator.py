import numpy as np
import json

def compute_branch_flows(net, vm, va):
    """Compute branch power flows from voltage solution.
    
    Returns lists of (pf, qf, pt, qt) for each branch, in pu.
    """
    branch = net['branch']
    from_idx = net['from_bus_idx']
    to_idx = net['to_bus_idx']
    branch_status = net['branch_status']
    nl = len(branch)
    
    branch_r = branch[:, 2]
    branch_x = branch[:, 3]
    branch_b = branch[:, 4]
    branch_tap = branch[:, 8].copy()
    branch_shift = branch[:, 9].copy() * np.pi / 180.0
    branch_tap[branch_tap == 0.0] = 1.0
    
    z_mag_sq = branch_r**2 + branch_x**2
    z_mag_sq[z_mag_sq == 0] = 1e-20
    g_s = branch_r / z_mag_sq
    b_s = -branch_x / z_mag_sq
    bc = branch_b
    
    pf_arr = np.zeros(nl)
    qf_arr = np.zeros(nl)
    pt_arr = np.zeros(nl)
    qt_arr = np.zeros(nl)
    
    for l in range(nl):
        if branch_status[l] <= 0:
            continue
        
        fi = from_idx[l]
        ti = to_idx[l]
        t = branch_tap[l]
        shift = branch_shift[l]
        g_br = g_s[l]
        b_br = b_s[l]
        bc_l = bc[l]
        
        vm_f = vm[fi]
        vm_t = vm[ti]
        va_f = va[fi]
        va_t = va[ti]
        
        delta = va_f - va_t - shift
        
        pf = g_br * vm_f**2 / t**2 - (vm_f * vm_t / t) * (g_br * np.cos(delta) + b_br * np.sin(delta))
        qf = -(b_br + bc_l/2) * vm_f**2 / t**2 - (vm_f * vm_t / t) * (g_br * np.sin(delta) - b_br * np.cos(delta))
        
        delta_r = va_t - va_f + shift
        pt = g_br * vm_t**2 - (vm_f * vm_t / t) * (g_br * np.cos(delta_r) + b_br * np.sin(delta_r))
        qt = -(b_br + bc_l/2) * vm_t**2 - (vm_f * vm_t / t) * (g_br * np.sin(delta_r) - b_br * np.cos(delta_r))
        
        pf_arr[l] = pf
        qf_arr[l] = qf
        pt_arr[l] = pt
        qt_arr[l] = qt
    
    return pf_arr, qf_arr, pt_arr, qt_arr


def compute_power_mismatches(net, vm, va, pg, qg):
    """Compute power balance mismatches at each bus.
    Returns max_p_mismatch_MW, max_q_mismatch_MVAr.
    """
    baseMVA = net['baseMVA']
    bus = net['bus']
    gen = net['gen']
    nb = len(bus)
    ng = len(gen)
    gen_bus_idx = net['gen_bus_idx']
    gen_status = net['gen_status']
    
    pf_arr, qf_arr, pt_arr, qt_arr = compute_branch_flows(net, vm, va)
    
    p_inj = np.zeros(nb)
    q_inj = np.zeros(nb)
    
    # Generator injections
    for k in range(ng):
        if gen_status[k] > 0:
            bidx = gen_bus_idx[k]
            p_inj[bidx] += pg[k]  # pu
            q_inj[bidx] += qg[k]  # pu
    
    # Loads and shunts
    for i in range(nb):
        pd = bus[i, 2] / baseMVA
        qd = bus[i, 3] / baseMVA
        gs = bus[i, 4] / baseMVA
        bs = bus[i, 5] / baseMVA
        p_inj[i] -= pd + gs * vm[i]**2
        q_inj[i] -= qd - bs * vm[i]**2
    
    # Branch flows
    branch = net['branch']
    from_idx = net['from_bus_idx']
    to_idx = net['to_bus_idx']
    branch_status = net['branch_status']
    nl = len(branch)
    
    for l in range(nl):
        if branch_status[l] <= 0:
            continue
        fi = from_idx[l]
        ti = to_idx[l]
        p_inj[fi] -= pf_arr[l]
        q_inj[fi] -= qf_arr[l]
        p_inj[ti] -= pt_arr[l]
        q_inj[ti] -= qt_arr[l]
    
    max_p = np.max(np.abs(p_inj)) * baseMVA
    max_q = np.max(np.abs(q_inj)) * baseMVA
    
    return max_p, max_q


def compute_feasibility(net, vm, va, pg, qg):
    """Compute all feasibility metrics."""
    baseMVA = net['baseMVA']
    bus = net['bus']
    branch = net['branch']
    nb = len(bus)
    nl = len(branch)
    
    max_p, max_q = compute_power_mismatches(net, vm, va, pg, qg)
    
    # Voltage violations
    vmin = bus[:, 12]
    vmax = bus[:, 11]
    v_viol = np.maximum(np.maximum(vmin - vm, 0), np.maximum(vm - vmax, 0))
    max_v_viol = np.max(v_viol)
    
    # Branch overload
    pf_arr, qf_arr, pt_arr, qt_arr = compute_branch_flows(net, vm, va)
    branch_status = net['branch_status']
    max_overload = 0.0
    
    for l in range(nl):
        if branch_status[l] <= 0:
            continue
        rateA = branch[l, 5]
        if rateA <= 0:
            continue
        sf = np.sqrt(pf_arr[l]**2 + qf_arr[l]**2) * baseMVA
        st = np.sqrt(pt_arr[l]**2 + qt_arr[l]**2) * baseMVA
        overload = max(sf - rateA, st - rateA, 0.0)
        max_overload = max(max_overload, overload)
    
    return {
        'max_p_mismatch_MW': round(max_p, 6),
        'max_q_mismatch_MVAr': round(max_q, 6),
        'max_voltage_violation_pu': round(max_v_viol, 6),
        'max_branch_overload_MVA': round(max_overload, 6),
    }


def find_most_loaded_branches(net, vm, va, top_k=10):
    """Find the top-k most loaded in-service branches with rateA > 0."""
    baseMVA = net['baseMVA']
    branch = net['branch']
    branch_status = net['branch_status']
    nl = len(branch)
    
    pf_arr, qf_arr, pt_arr, qt_arr = compute_branch_flows(net, vm, va)
    
    loadings = []
    for l in range(nl):
        if branch_status[l] <= 0:
            continue
        rateA = branch[l, 5]
        if rateA <= 0:
            continue
        
        sf = np.sqrt(pf_arr[l]**2 + qf_arr[l]**2) * baseMVA
        st = np.sqrt(pt_arr[l]**2 + qt_arr[l]**2) * baseMVA
        max_flow = max(sf, st)
        loading_pct = max_flow / rateA * 100.0
        
        loadings.append({
            'branch_idx': l,
            'from_bus': int(branch[l, 0]),
            'to_bus': int(branch[l, 1]),
            'loading_pct': loading_pct,
            'flow_from_MVA': sf,
            'flow_to_MVA': st,
            'limit_MVA': rateA,
        })
    
    # Sort by loading_pct descending, then by branch index for tie-breaking
    loadings.sort(key=lambda x: (-x['loading_pct'], x['branch_idx']))
    
    return loadings[:top_k]


def generate_report(net, sol, output_path):
    """Generate the full report.json from network data and solution."""
    baseMVA = net['baseMVA']
    bus = net['bus']
    gen = net['gen']
    nb = len(bus)
    ng = len(gen)
    
    vm = sol['vm']
    va = sol['va']  # radians
    pg = sol['pg']  # pu
    qg = sol['qg']  # pu
    
    gen_status = net['gen_status']
    
    # Total load
    total_load_MW = float(np.sum(bus[:, 2]))
    total_load_MVAr = float(np.sum(bus[:, 3]))
    
    # Total generation
    total_gen_MW = 0.0
    total_gen_MVAr = 0.0
    for k in range(ng):
        if gen_status[k] > 0:
            total_gen_MW += pg[k] * baseMVA
            total_gen_MVAr += qg[k] * baseMVA
    
    total_losses_MW = total_gen_MW - total_load_MW
    
    # Recompute cost from solution values
    gencost = net['gencost']
    total_cost = 0.0
    for k in range(ng):
        if gen_status[k] > 0:
            pg_mw = pg[k] * baseMVA
            ncost = int(gencost[k, 3])
            if ncost == 3:
                c2 = gencost[k, 4]
                c1 = gencost[k, 5]
                c0 = gencost[k, 6]
            elif ncost == 2:
                c2 = 0.0
                c1 = gencost[k, 4]
                c0 = gencost[k, 5]
            else:
                c2 = 0.0
                c1 = 0.0
                c0 = gencost[k, 4] if ncost >= 1 else 0.0
            total_cost += c2 * pg_mw**2 + c1 * pg_mw + c0
    
    # Map solver status
    status_str = sol['status']
    if 'Solve_Succeeded' in status_str or 'Optimal' in status_str.lower():
        solver_status = 'optimal'
    elif 'acceptable' in status_str.lower():
        solver_status = 'optimal'
    else:
        solver_status = status_str
    
    # Generators report
    generators = []
    for k in range(ng):
        gen_entry = {
            'id': k + 1,  # 1-indexed
            'bus': int(gen[k, 0]),
            'pg_MW': round(float(pg[k] * baseMVA), 6),
            'qg_MVAr': round(float(qg[k] * baseMVA), 6),
            'pmin_MW': float(gen[k, 9]),
            'pmax_MW': float(gen[k, 8]),
            'qmin_MVAr': float(gen[k, 4]),
            'qmax_MVAr': float(gen[k, 3]),
        }
        generators.append(gen_entry)
    
    # Buses report
    bus_ids = net['bus_ids']
    buses = []
    for i in range(nb):
        bus_entry = {
            'id': int(bus_ids[i]),
            'vm_pu': round(float(vm[i]), 6),
            'va_deg': round(float(va[i] * 180.0 / np.pi), 6),
            'vmin_pu': float(bus[i, 12]),
            'vmax_pu': float(bus[i, 11]),
        }
        buses.append(bus_entry)
    
    # Most loaded branches
    most_loaded = find_most_loaded_branches(net, vm, va, top_k=10)
    most_loaded_branches = []
    for ml in most_loaded:
        most_loaded_branches.append({
            'from_bus': ml['from_bus'],
            'to_bus': ml['to_bus'],
            'loading_pct': round(ml['loading_pct'], 6),
            'flow_from_MVA': round(ml['flow_from_MVA'], 6),
            'flow_to_MVA': round(ml['flow_to_MVA'], 6),
            'limit_MVA': ml['limit_MVA'],
        })
    
    # Feasibility check
    feasibility = compute_feasibility(net, vm, va, pg, qg)
    
    report = {
        'summary': {
            'total_cost_per_hour': round(total_cost, 2),
            'total_load_MW': round(total_load_MW, 2),
            'total_load_MVAr': round(total_load_MVAr, 2),
            'total_generation_MW': round(total_gen_MW, 2),
            'total_generation_MVAr': round(total_gen_MVAr, 2),
            'total_losses_MW': round(total_losses_MW, 2),
            'solver_status': solver_status,
        },
        'generators': generators,
        'buses': buses,
        'most_loaded_branches': most_loaded_branches,
        'feasibility_check': feasibility,
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report
