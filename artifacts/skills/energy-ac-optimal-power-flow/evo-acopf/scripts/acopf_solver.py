import numpy as np
import casadi as ca

def solve_acopf(net):
    """Solve AC OPF using CasADi + IPOPT.
    
    Args:
        net: dict from load_network()
    
    Returns:
        dict with solution: vm, va, pg, qg, solver_status, cost
    """
    baseMVA = net['baseMVA']
    bus = net['bus']
    gen = net['gen']
    branch = net['branch']
    gencost = net['gencost']
    
    nb = len(bus)  # number of buses
    ng = len(gen)  # number of generators
    nl = len(branch)  # number of branches
    
    bus_id_to_idx = net['bus_id_to_idx']
    gen_bus_idx = net['gen_bus_idx']
    ref_buses = net['ref_buses']
    from_idx = net['from_bus_idx']
    to_idx = net['to_bus_idx']
    gen_status = net['gen_status']
    branch_status = net['branch_status']
    
    # ---- Decision variables ----
    # vm: voltage magnitudes (nb)
    # va: voltage angles (nb)
    # pg: generator active power in pu (ng)
    # qg: generator reactive power in pu (ng)
    
    vm = ca.MX.sym('vm', nb)
    va = ca.MX.sym('va', nb)
    pg = ca.MX.sym('pg', ng)
    qg = ca.MX.sym('qg', ng)
    
    x = ca.vertcat(vm, va, pg, qg)
    
    # ---- Bounds ----
    vm_lb = bus[:, 12]  # VMIN
    vm_ub = bus[:, 11]  # VMAX
    
    va_lb = -np.full(nb, np.pi)  # angle bounds
    va_ub = np.full(nb, np.pi)
    
    # Fix reference bus angle to 0
    for r in ref_buses:
        va_lb[r] = 0.0
        va_ub[r] = 0.0
    
    pg_lb = np.zeros(ng)
    pg_ub = np.zeros(ng)
    qg_lb = np.zeros(ng)
    qg_ub = np.zeros(ng)
    
    for k in range(ng):
        if gen_status[k] > 0:
            pg_lb[k] = gen[k, 9] / baseMVA  # PMIN
            pg_ub[k] = gen[k, 8] / baseMVA  # PMAX
            qg_lb[k] = gen[k, 4] / baseMVA  # QMIN
            qg_ub[k] = gen[k, 3] / baseMVA  # QMAX
        else:
            pg_lb[k] = 0.0
            pg_ub[k] = 0.0
            qg_lb[k] = 0.0
            qg_ub[k] = 0.0
    
    x_lb = np.concatenate([vm_lb, va_lb, pg_lb, qg_lb])
    x_ub = np.concatenate([vm_ub, va_ub, pg_ub, qg_ub])
    
    # ---- Initial point ----
    vm0 = bus[:, 7].copy()  # VM from data
    va0 = bus[:, 8].copy() * np.pi / 180.0  # VA from data, convert to radians
    pg0 = gen[:, 1].copy() / baseMVA  # PG from data
    qg0 = gen[:, 2].copy() / baseMVA  # QG from data
    
    # Clip to bounds
    vm0 = np.clip(vm0, vm_lb, vm_ub)
    for r in ref_buses:
        va0[r] = 0.0
    pg0 = np.clip(pg0, pg_lb, pg_ub)
    qg0 = np.clip(qg0, qg_lb, qg_ub)
    
    x0 = np.concatenate([vm0, va0, pg0, qg0])
    
    # ---- Objective: minimize generation cost ----
    # Cost = sum c2*Pg_MW^2 + c1*Pg_MW + c0
    # Pg_MW = pg * baseMVA
    obj = 0
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
            obj += c2 * pg_mw**2 + c1 * pg_mw + c0
    
    # ---- Constraints ----
    g_list = []  # constraint expressions
    g_lb_list = []  # lower bounds
    g_ub_list = []  # upper bounds
    
    # Power balance at each bus
    # P_inj[i] = sum(pg at bus i) - Pd[i]/baseMVA - Gs[i]*vm[i]^2/baseMVA
    # Q_inj[i] = sum(qg at bus i) - Qd[i]/baseMVA + Bs[i]*vm[i]^2/baseMVA
    # These must equal sum of branch flows out of bus i
    
    # Precompute branch parameters
    branch_r = branch[:, 2]
    branch_x = branch[:, 3]
    branch_b = branch[:, 4]  # total charging susceptance
    branch_rateA = branch[:, 5]
    branch_tap = branch[:, 8].copy()
    branch_shift = branch[:, 9].copy() * np.pi / 180.0  # to radians
    
    # tap = 0 means 1.0
    branch_tap[branch_tap == 0.0] = 1.0
    
    # Compute series admittance
    # y = 1/(r + jx) = (r - jx)/(r^2 + x^2)
    # g_s = r/(r^2+x^2), b_s = -x/(r^2+x^2)
    z_mag_sq = branch_r**2 + branch_x**2
    # Avoid division by zero
    z_mag_sq[z_mag_sq == 0] = 1e-20
    g_s = branch_r / z_mag_sq
    b_s = -branch_x / z_mag_sq
    
    bc = branch_b  # total charging susceptance
    
    # Build power injection expressions for each bus
    p_inj = [0.0] * nb
    q_inj = [0.0] * nb
    
    # Add generator contributions
    for k in range(ng):
        if gen_status[k] > 0:
            bidx = gen_bus_idx[k]
            p_inj[bidx] = p_inj[bidx] + pg[k]
            q_inj[bidx] = q_inj[bidx] + qg[k]
    
    # Subtract loads and shunts
    for i in range(nb):
        pd = bus[i, 2] / baseMVA  # PD
        qd = bus[i, 3] / baseMVA  # QD
        gs = bus[i, 4] / baseMVA  # GS
        bs = bus[i, 5] / baseMVA  # BS
        p_inj[i] = p_inj[i] - pd - gs * vm[i]**2
        q_inj[i] = q_inj[i] - qd + bs * vm[i]**2
    
    # Compute branch flows and subtract from bus injections
    # Also collect flow constraints
    branch_pf = []  # P_ij (from side) in pu
    branch_qf = []  # Q_ij (from side) in pu
    branch_pt = []  # P_ji (to side) in pu
    branch_qt = []  # Q_ji (to side) in pu
    
    for l in range(nl):
        if branch_status[l] <= 0:
            branch_pf.append(0.0)
            branch_qf.append(0.0)
            branch_pt.append(0.0)
            branch_qt.append(0.0)
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
        
        # From side (tap side): P_ij and Q_ij
        pf = g_br * vm_f**2 / t**2 - (vm_f * vm_t / t) * (g_br * ca.cos(delta) + b_br * ca.sin(delta))
        qf = -(b_br + bc_l/2) * vm_f**2 / t**2 - (vm_f * vm_t / t) * (g_br * ca.sin(delta) - b_br * ca.cos(delta))
        
        # To side: P_ji and Q_ji
        delta_r = va_t - va_f + shift
        pt = g_br * vm_t**2 - (vm_f * vm_t / t) * (g_br * ca.cos(delta_r) + b_br * ca.sin(delta_r))
        qt = -(b_br + bc_l/2) * vm_t**2 - (vm_f * vm_t / t) * (g_br * ca.sin(delta_r) - b_br * ca.cos(delta_r))
        
        branch_pf.append(pf)
        branch_qf.append(qf)
        branch_pt.append(pt)
        branch_qt.append(qt)
        
        # Subtract flows from bus injections
        p_inj[fi] = p_inj[fi] - pf
        q_inj[fi] = q_inj[fi] - qf
        p_inj[ti] = p_inj[ti] - pt
        q_inj[ti] = q_inj[ti] - qt
    
    # Power balance constraints: p_inj[i] = 0, q_inj[i] = 0
    for i in range(nb):
        g_list.append(p_inj[i])
        g_lb_list.append(0.0)
        g_ub_list.append(0.0)
        g_list.append(q_inj[i])
        g_lb_list.append(0.0)
        g_ub_list.append(0.0)
    
    # Branch flow limits: |S_ij|^2 <= (rateA/baseMVA)^2
    for l in range(nl):
        if branch_status[l] <= 0:
            continue
        rateA = branch_rateA[l]
        if rateA <= 0:
            continue
        
        smax = rateA / baseMVA
        smax_sq = smax**2
        
        # From side
        sf_sq = branch_pf[l]**2 + branch_qf[l]**2
        g_list.append(sf_sq)
        g_lb_list.append(-1e20)
        g_ub_list.append(smax_sq)
        
        # To side
        st_sq = branch_pt[l]**2 + branch_qt[l]**2
        g_list.append(st_sq)
        g_lb_list.append(-1e20)
        g_ub_list.append(smax_sq)
    
    # Angle difference constraints
    for l in range(nl):
        if branch_status[l] <= 0:
            continue
        fi = from_idx[l]
        ti = to_idx[l]
        angmin = branch[l, 11] * np.pi / 180.0
        angmax = branch[l, 12] * np.pi / 180.0
        
        g_list.append(va[fi] - va[ti])
        g_lb_list.append(angmin)
        g_ub_list.append(angmax)
    
    # Assemble constraints
    g_expr = ca.vertcat(*g_list)
    g_lb = np.array(g_lb_list)
    g_ub = np.array(g_ub_list)
    
    # ---- Solve ----
    nlp = {'x': x, 'f': obj, 'g': g_expr}
    opts = {
        'ipopt.max_iter': 2000,
        'ipopt.tol': 1e-6,
        'ipopt.acceptable_tol': 1e-5,
        'ipopt.print_level': 3,
        'print_time': 0,
        'ipopt.mu_strategy': 'adaptive',
        'ipopt.warm_start_init_point': 'yes',
        'ipopt.linear_solver': 'mumps',
    }
    
    solver = ca.nlpsol('solver', 'ipopt', nlp, opts)
    
    sol = solver(
        x0=x0,
        lbx=x_lb,
        ubx=x_ub,
        lbg=g_lb,
        ubg=g_ub,
    )
    
    # Extract solution
    x_sol = np.array(sol['x']).flatten()
    vm_sol = x_sol[:nb]
    va_sol = x_sol[nb:2*nb]
    pg_sol = x_sol[2*nb:2*nb+ng]
    qg_sol = x_sol[2*nb+ng:2*nb+2*ng]
    
    # Get solver status
    stats = solver.stats()
    status = stats['return_status']
    
    cost = float(sol['f'])
    
    return {
        'vm': vm_sol,
        'va': va_sol,  # in radians
        'pg': pg_sol,  # in pu
        'qg': qg_sol,  # in pu
        'status': status,
        'cost': cost,
        'baseMVA': baseMVA,
    }
