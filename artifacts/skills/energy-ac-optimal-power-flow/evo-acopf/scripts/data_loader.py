import json
import numpy as np

def load_network(filepath):
    """Load MATPOWER-format network from JSON file.
    Returns a dict with parsed arrays and mappings."""
    with open(filepath) as f:
        data = json.load(f)
    
    baseMVA = data['baseMVA']
    bus = np.array(data['bus'])
    gen = np.array(data['gen'])
    branch = np.array(data['branch'])
    gencost = np.array(data['gencost'])
    
    # Filter in-service generators and branches
    gen_status = gen[:, 7]
    branch_status = branch[:, 10]
    
    # Build bus ID to index mapping
    bus_ids = bus[:, 0].astype(int)
    bus_id_to_idx = {bid: idx for idx, bid in enumerate(bus_ids)}
    
    # Find reference bus
    ref_buses = []
    for i in range(len(bus)):
        if int(bus[i, 1]) == 3:
            ref_buses.append(i)
    
    # Build generator-to-bus mapping
    gen_buses = gen[:, 0].astype(int)  # bus numbers
    gen_bus_idx = np.array([bus_id_to_idx[b] for b in gen_buses])
    
    # Build branch bus indices
    from_bus = branch[:, 0].astype(int)
    to_bus = branch[:, 1].astype(int)
    from_bus_idx = np.array([bus_id_to_idx[b] for b in from_bus])
    to_bus_idx = np.array([bus_id_to_idx[b] for b in to_bus])
    
    return {
        'baseMVA': baseMVA,
        'bus': bus,
        'gen': gen,
        'branch': branch,
        'gencost': gencost,
        'bus_ids': bus_ids,
        'bus_id_to_idx': bus_id_to_idx,
        'ref_buses': ref_buses,
        'gen_bus_idx': gen_bus_idx,
        'gen_status': gen_status,
        'branch_status': branch_status,
        'from_bus_idx': from_bus_idx,
        'to_bus_idx': to_bus_idx,
    }
