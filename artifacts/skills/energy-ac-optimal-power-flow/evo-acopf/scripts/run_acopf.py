"""End-to-end ACOPF entry point."""
import sys
import os

def run_acopf_pipeline(network_path, output_path):
    """Load network, solve ACOPF, generate report."""
    # Add scripts dir to path
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    
    from data_loader import load_network
    from acopf_solver import solve_acopf
    from report_generator import generate_report
    
    print("Loading network...")
    net = load_network(network_path)
    print(f"  Buses: {len(net['bus'])}, Gens: {len(net['gen'])}, Branches: {len(net['branch'])}")
    
    print("Solving ACOPF...")
    sol = solve_acopf(net)
    print(f"  Status: {sol['status']}")
    print(f"  Cost: {sol['cost']:.2f}")
    
    print("Generating report...")
    report = generate_report(net, sol, output_path)
    print(f"  Total cost: {report['summary']['total_cost_per_hour']}")
    print(f"  Total gen MW: {report['summary']['total_generation_MW']}")
    print(f"  Total load MW: {report['summary']['total_load_MW']}")
    print(f"  Losses MW: {report['summary']['total_losses_MW']}")
    print(f"  Max P mismatch: {report['feasibility_check']['max_p_mismatch_MW']}")
    print(f"  Max Q mismatch: {report['feasibility_check']['max_q_mismatch_MVAr']}")
    print(f"  Solver status: {report['summary']['solver_status']}")
    print(f"Report written to {output_path}")
    
    return report


def validate_report(report_path, network_path):
    """Validate a report against the network data."""
    import json
    import numpy as np
    
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from data_loader import load_network
    from report_generator import compute_branch_flows, compute_feasibility
    
    with open(report_path) as f:
        report = json.load(f)
    
    net = load_network(network_path)
    
    errors = []
    
    # Check structure
    required_keys = ['summary', 'generators', 'buses', 'most_loaded_branches', 'feasibility_check']
    for k in required_keys:
        if k not in report:
            errors.append(f"Missing key: {k}")
    
    # Check generator count
    if len(report['generators']) != len(net['gen']):
        errors.append(f"Generator count mismatch: {len(report['generators'])} vs {len(net['gen'])}")
    
    # Check bus count
    if len(report['buses']) != len(net['bus']):
        errors.append(f"Bus count mismatch: {len(report['buses'])} vs {len(net['bus'])}")
    
    # Check most_loaded_branches count
    if len(report['most_loaded_branches']) != 10:
        errors.append(f"most_loaded_branches should have 10 entries, got {len(report['most_loaded_branches'])}")
    
    # Check total generation matches sum of individual generators
    gen_sum_MW = sum(g['pg_MW'] for g in report['generators'])
    if abs(gen_sum_MW - report['summary']['total_generation_MW']) > 0.1:
        errors.append(f"Gen MW sum mismatch: {gen_sum_MW:.2f} vs {report['summary']['total_generation_MW']}")
    
    gen_sum_MVAr = sum(g['qg_MVAr'] for g in report['generators'])
    if abs(gen_sum_MVAr - report['summary']['total_generation_MVAr']) > 0.1:
        errors.append(f"Gen MVAr sum mismatch: {gen_sum_MVAr:.2f} vs {report['summary']['total_generation_MVAr']}")
    
    # Check losses = gen - load
    expected_losses = report['summary']['total_generation_MW'] - report['summary']['total_load_MW']
    if abs(expected_losses - report['summary']['total_losses_MW']) > 0.1:
        errors.append(f"Losses mismatch: {expected_losses:.2f} vs {report['summary']['total_losses_MW']}")
    
    # Check solver status
    if report['summary']['solver_status'] != 'optimal':
        errors.append(f"Solver status: {report['summary']['solver_status']}")
    
    # Check feasibility
    feas = report['feasibility_check']
    if feas['max_p_mismatch_MW'] > 1.0:
        errors.append(f"Large P mismatch: {feas['max_p_mismatch_MW']}")
    if feas['max_q_mismatch_MVAr'] > 1.0:
        errors.append(f"Large Q mismatch: {feas['max_q_mismatch_MVAr']}")
    
    if errors:
        print("Validation FAILED:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("Validation PASSED")
    
    return errors


if __name__ == '__main__':
    network_path = sys.argv[1] if len(sys.argv) > 1 else '/root/network.json'
    output_path = sys.argv[2] if len(sys.argv) > 2 else '/root/report.json'
    
    report = run_acopf_pipeline(network_path, output_path)
    errors = validate_report(output_path, network_path)
    if errors:
        sys.exit(1)
