---
name: evo-pcap-analysis
description: "Analyze PCAP files to compute network statistics and fill a CSV template. Dynamically discovers metrics from the template and resolves them from computed data. Use when given a packets.pcap and a stats CSV template to fill."
---

# PCAP Network Statistics Analysis

This skill analyzes PCAP files and fills a CSV template with computed network statistics.
Metric names are discovered from the template at runtime - no hardcoded metric names.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-pcap-analysis/scripts')
from pcap_stats import run_end_to_end

pcap_path = '/root/packets.pcap'
template_path = '/root/network_stats.csv'
output_path = '/root/network_stats.csv'

results, ok = run_end_to_end(pcap_path, template_path, output_path)
if not ok:
    print("Validation failed!")
else:
    print("Done - all metrics filled")
```

## Architecture

- `load_packets(path)` - Load PCAP with Scapy (handles VLAN, tunnels)
- `count_protocols(packets)` - Independent layer checks per protocol
- `compute_rate_buckets(timestamps, bucket_size)` - Relative time bucketing
- `compute_size_stats(packets)` - Full frame length stats
- `shannon_entropy(values)` - Shannon entropy in bits
- `compute_graph(packets)` - Directed IP graph topology
- `compute_iat(timestamps)` - Inter-arrival time with population variance
- `compute_pcr(packets)` - Producer/Consumer ratio per IP
- `compute_flows(packets)` - 5-tuple flow analysis
- `detect_port_scan(packets)` - Converging evidence detection
- `detect_dos(buckets)` - Rate spike detection
- `detect_beaconing(iat_stats)` - Low CV detection
- `resolve_metric(name, computed)` - Dynamic name-to-value resolution
- `analyze_and_resolve(pcap, template)` - Full pipeline with template discovery
- `validate_csv(path)` - Check all template lines have values
