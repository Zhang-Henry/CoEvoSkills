import math
import collections
from scapy.all import rdpcap, IP, TCP, UDP, ICMP, ARP


def load_packets(pcap_path):
    """Load packets from a PCAP file."""
    return rdpcap(pcap_path)


def extract_timestamps(packets):
    """Extract sorted timestamps from packets."""
    return sorted(float(pkt.time) for pkt in packets)


def count_protocols(packets):
    """Count packets by protocol. Each check is independent."""
    counts = {}
    layer_map = {'tcp': TCP, 'udp': UDP, 'icmp': ICMP, 'arp': ARP}
    for key, layer_cls in layer_map.items():
        counts[key] = sum(1 for pkt in packets if layer_cls in pkt)
    counts['ip_total'] = sum(1 for pkt in packets if IP in pkt)
    return counts


def compute_duration(timestamps):
    if len(timestamps) < 2:
        return 0.0
    return timestamps[-1] - timestamps[0]


def compute_rate_buckets(timestamps, bucket_size=60):
    if not timestamps:
        return []
    start = timestamps[0]
    buckets = collections.Counter()
    for ts in timestamps:
        bucket_idx = int((ts - start) // bucket_size)
        buckets[bucket_idx] += 1
    max_bucket = max(buckets.keys())
    return [buckets.get(i, 0) for i in range(max_bucket + 1)]


def compute_size_stats(packets):
    sizes = [len(pkt) for pkt in packets]
    if not sizes:
        return {'total': 0, 'avg': 0, 'min': 0, 'max': 0}
    return {
        'total': sum(sizes),
        'avg': sum(sizes) / len(sizes),
        'min': min(sizes),
        'max': max(sizes),
    }


def shannon_entropy(values):
    if not values:
        return 0.0
    counter = collections.Counter(values)
    total = len(values)
    ent = 0.0
    for count in counter.values():
        if count > 0:
            p = count / total
            ent -= p * math.log2(p)
    return ent


def extract_ip_port_data(packets):
    src_ips, dst_ips = [], []
    src_ports, dst_ports = [], []
    for pkt in packets:
        if IP in pkt:
            src_ips.append(pkt[IP].src)
            dst_ips.append(pkt[IP].dst)
        if TCP in pkt:
            src_ports.append(pkt[TCP].sport)
            dst_ports.append(pkt[TCP].dport)
        elif UDP in pkt:
            src_ports.append(pkt[UDP].sport)
            dst_ports.append(pkt[UDP].dport)
    return src_ips, dst_ips, src_ports, dst_ports


def compute_graph(packets):
    nodes = set()
    edges = set()
    out_targets = collections.defaultdict(set)
    in_sources = collections.defaultdict(set)
    for pkt in packets:
        if IP in pkt:
            src, dst = pkt[IP].src, pkt[IP].dst
            nodes.add(src)
            nodes.add(dst)
            edges.add((src, dst))
            out_targets[src].add(dst)
            in_sources[dst].add(src)
    n, e = len(nodes), len(edges)
    density = e / (n * (n - 1)) if n >= 2 else 0.0
    max_out = max((len(v) for v in out_targets.values()), default=0)
    max_in = max((len(v) for v in in_sources.values()), default=0)
    return {'nodes': n, 'edges': e, 'density': density, 'max_out': max_out, 'max_in': max_in}


def compute_iat(timestamps):
    if len(timestamps) < 2:
        return {'mean': 0, 'variance': 0, 'cv': 0}
    iats = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    mean_v = sum(iats) / len(iats)
    var_v = sum((x - mean_v)**2 for x in iats) / len(iats)
    std_v = math.sqrt(var_v)
    cv_v = std_v / mean_v if mean_v > 0 else 0
    return {'mean': mean_v, 'variance': var_v, 'cv': cv_v}


def compute_pcr(packets):
    bytes_sent = collections.defaultdict(int)
    bytes_recv = collections.defaultdict(int)
    for pkt in packets:
        if IP in pkt:
            pkt_len = len(pkt)
            bytes_sent[pkt[IP].src] += pkt_len
            bytes_recv[pkt[IP].dst] += pkt_len
    all_ips = set(bytes_sent.keys()) | set(bytes_recv.keys())
    producers, consumers = 0, 0
    for ip in all_ips:
        s, r = bytes_sent.get(ip, 0), bytes_recv.get(ip, 0)
        t = s + r
        if t == 0:
            continue
        pcr = (s - r) / t
        if pcr > 0.2:
            producers += 1
        elif pcr < -0.2:
            consumers += 1
    return producers, consumers


def compute_flows(packets):
    flows = set()
    for pkt in packets:
        if IP in pkt:
            src_ip, dst_ip = pkt[IP].src, pkt[IP].dst
            if TCP in pkt:
                flows.add((src_ip, dst_ip, pkt[TCP].sport, pkt[TCP].dport, 6))
            elif UDP in pkt:
                flows.add((src_ip, dst_ip, pkt[UDP].sport, pkt[UDP].dport, 17))
    tcp_f = sum(1 for f in flows if f[4] == 6)
    udp_f = sum(1 for f in flows if f[4] == 17)
    bidir = 0
    for f in flows:
        rev = (f[1], f[0], f[3], f[2], f[4])
        if rev in flows:
            bidir += 1
    bidir //= 2
    return {'total': len(flows), 'tcp': tcp_f, 'udp': udp_f, 'bidir': bidir}


def detect_port_scan(packets):
    src_dst_ports = collections.defaultdict(set)
    src_syn = collections.defaultdict(int)
    src_tcp_total = collections.defaultdict(int)
    for pkt in packets:
        if IP in pkt and TCP in pkt:
            src = pkt[IP].src
            src_dst_ports[src].add(pkt[TCP].dport)
            src_tcp_total[src] += 1
            flags = pkt[TCP].flags
            if flags == 'S' or flags == 0x02:
                src_syn[src] += 1
    for src, ports in src_dst_ports.items():
        n_ports = len(ports)
        total = src_tcp_total[src]
        if n_ports > 100 and total > 0:
            if src_syn[src] / total > 0.5:
                return True
    return False


def detect_dos(bucket_counts):
    if not bucket_counts:
        return False
    avg_r = sum(bucket_counts) / len(bucket_counts)
    max_r = max(bucket_counts)
    return avg_r > 0 and (max_r / avg_r) > 10


def detect_beaconing(iat_stats):
    return iat_stats['cv'] < 0.5 and iat_stats['mean'] > 0


def resolve_metric(name, computed):
    """Resolve a metric name discovered from the template to a computed value.
    
    This function dynamically maps arbitrary metric names to computed results
    by parsing the metric name structure at runtime.
    """
    proto = computed['proto']
    sizes = computed['sizes']
    graph = computed['graph']
    iat = computed['iat']
    flows = computed['flows']
    entropy_data = computed['entropy']
    bucket_counts = computed['buckets']
    flags = computed['flags']

    # Layer-based counters
    if name.startswith('protocol_'):
        suffix = name[len('protocol_'):]
        if suffix in proto:
            return proto[suffix]

    # Duration
    if 'duration' in name and 'second' in name:
        return round(computed['duration'], 6)

    # Rate buckets: any metric containing 'per_minute' or 'ppm'
    if 'per_minute' in name or 'ppm' in name:
        if not bucket_counts:
            return 0
        if 'avg' in name or 'mean' in name:
            return round(sum(bucket_counts) / len(bucket_counts), 6)
        if 'max' in name:
            return max(bucket_counts)
        if 'min' in name:
            return min(bucket_counts)

    # Packet length aggregates
    if name == 'total_bytes':
        return sizes['total']
    if 'avg' in name and 'packet' in name and 'size' in name:
        return round(sizes['avg'], 6)
    if 'min' in name and 'packet' in name and 'size' in name:
        return sizes['min']
    if 'max' in name and 'packet' in name and 'size' in name:
        return sizes['max']

    # Shannon information measures
    if 'entropy' in name:
        if 'src' in name and 'ip' in name:
            return round(entropy_data['src_ip_ent'], 6)
        if 'dst' in name and 'ip' in name:
            return round(entropy_data['dst_ip_ent'], 6)
        if 'src' in name and 'port' in name:
            return round(entropy_data['src_port_ent'], 6)
        if 'dst' in name and 'port' in name:
            return round(entropy_data['dst_port_ent'], 6)

    # Unique ports
    if 'unique' in name and 'port' in name:
        if 'src' in name:
            return entropy_data['unique_src_ports']
        if 'dst' in name:
            return entropy_data['unique_dst_ports']

    # Directed communication topology
    if name == 'num_nodes':
        return graph['nodes']
    if name == 'num_edges':
        return graph['edges']
    if 'density' in name:
        return round(graph['density'], 6)
    if 'indegree' in name:
        return graph['max_in']
    if 'outdegree' in name:
        return graph['max_out']

    # IAT
    if name.startswith('iat_'):
        suffix = name[4:]
        if suffix in iat:
            return round(iat[suffix], 6)

    # PCR
    if 'producer' in name:
        return computed['producers']
    if 'consumer' in name:
        return computed['consumers']

    # Connection tuple aggregates
    if name == 'unique_flows':
        return flows['total']
    if 'bidirectional' in name:
        return flows['bidir']
    if name == 'tcp_flows':
        return flows['tcp']
    if name == 'udp_flows':
        return flows['udp']

    # Boolean flags
    if name in flags:
        return flags[name]

    return None


def analyze_and_resolve(pcap_path, template_path):
    """Analyze PCAP and resolve all metrics discovered from the template."""
    packets = load_packets(pcap_path)
    print(f"Loaded {len(packets)} packets")

    timestamps = extract_timestamps(packets)
    proto = count_protocols(packets)
    duration = compute_duration(timestamps)
    buckets = compute_rate_buckets(timestamps, 60)
    sizes = compute_size_stats(packets)
    src_ips, dst_ips, src_ports, dst_ports = extract_ip_port_data(packets)
    graph = compute_graph(packets)
    iat = compute_iat(timestamps)
    producers, consumers = compute_pcr(packets)
    flows = compute_flows(packets)

    has_scan = detect_port_scan(packets)
    has_dos = detect_dos(buckets)
    has_beacon = detect_beaconing(iat)
    is_benign = not (has_scan or has_dos or has_beacon)

    entropy_data = {
        'src_ip_ent': shannon_entropy(src_ips),
        'dst_ip_ent': shannon_entropy(dst_ips),
        'src_port_ent': shannon_entropy(src_ports),
        'dst_port_ent': shannon_entropy(dst_ports),
        'unique_src_ports': len(set(src_ports)),
        'unique_dst_ports': len(set(dst_ports)),
    }

    flags = {
        'is_traffic_benign': str(is_benign).lower(),
        'has_port_scan': str(has_scan).lower(),
        'has_dos_pattern': str(has_dos).lower(),
        'has_beaconing': str(has_beacon).lower(),
    }

    computed = {
        'proto': proto, 'duration': duration, 'buckets': buckets,
        'sizes': sizes, 'entropy': entropy_data, 'graph': graph,
        'iat': iat, 'producers': producers, 'consumers': consumers,
        'flows': flows, 'flags': flags,
    }

    # Discover metrics from template
    metrics_needed = []
    with open(template_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('metric'):
                continue
            parts = line.split(',')
            metrics_needed.append(parts[0].strip())

    results = {}
    for m in metrics_needed:
        val = resolve_metric(m, computed)
        if val is not None:
            results[m] = val
        else:
            print(f"WARNING: Could not resolve metric '{m}'")

    return results


def write_csv(results, template_path, output_path):
    lines = []
    with open(template_path, 'r') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('#') or line.startswith('metric'):
                lines.append(line)
                continue
            parts = line.split(',')
            metric = parts[0].strip()
            if metric in results:
                lines.append(f"{metric},{results[metric]}")
            else:
                lines.append(line)
    with open(output_path, 'w') as f:
        for line in lines:
            f.write(line + '\n')
    print(f"Results written to {output_path}")


def validate_csv(output_path):
    missing = []
    with open(output_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('metric'):
                continue
            parts = line.split(',')
            if len(parts) < 2 or not parts[1].strip():
                missing.append(parts[0].strip())
    if missing:
        print(f"VALIDATION FAILED - Missing: {missing}")
        return False
    print("VALIDATION PASSED")
    return True


def run_end_to_end(pcap_path, template_path, output_path):
    """End-to-end: analyze PCAP, write CSV from template, validate."""
    results = analyze_and_resolve(pcap_path, template_path)
    write_csv(results, template_path, output_path)
    ok = validate_csv(output_path)
    for k, v in sorted(results.items()):
        print(f"  {k}: {v}")
    return results, ok
