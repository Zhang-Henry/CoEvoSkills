# Network Traffic Analysis and Intrusion Detection from Packet Captures

This document provides background on extracting network statistics from packet captures (PCAP files), computing derived metrics used in intrusion detection, and interpreting those metrics to classify traffic behavior.

## Packet Capture Structure and Protocol Layers

A PCAP file contains a sequence of captured network packets, each with a timestamp and raw frame data. Packets are layered according to the OSI model, and a single packet may contain multiple nested protocol headers. Understanding which layers are present in a given packet is essential for correctly counting protocols and extracting fields.

**Important:** PCAP files may contain VLAN-tagged frames (802.1Q), tunneled packets, or other non-standard encapsulations where the IP layer is not at a fixed offset from the Ethernet header. A PCAP parser must perform deep protocol dissection to correctly identify IP layers inside such encapsulations. Libraries that use fixed-offset parsing will miss these packets entirely, producing incorrect protocol counts and all derived metrics (graph topology, flows, entropy, PCR). Scapy is the recommended tool for this reason --- it automatically handles VLAN tags, tunnels, and nested encapsulations.

**Layer 2 (Data Link):** The outermost header is typically Ethernet. ARP (Address Resolution Protocol) operates at this layer --- ARP packets do **not** contain an IP layer. When counting "packets that contain an IP layer," ARP packets must be excluded.

**Layer 3 (Network):** In this context, "IP" refers exclusively to **IPv4**. IPv6 packets, if present in the capture, should be ignored for all IP-related metrics (protocol counts, IP entropy, graph topology, flows, PCR). Every TCP, UDP, and ICMP packet is encapsulated within an IPv4 header, but not every IPv4 packet contains a transport-layer header (e.g., IP fragments, or protocols other than TCP/UDP/ICMP). In Scapy, checking `IP in packet` tests for the IPv4 layer specifically.

**Layer 4 (Transport):** TCP and UDP packets carry source and destination port numbers. ICMP packets do not have ports. When computing port-based statistics (entropy, unique port counts, flow keys), only TCP and UDP packets contribute. Note that ICMPv6 (part of IPv6) is not the same as ICMP (IPv4) --- only IPv4 ICMP packets should be counted as `protocol_icmp`.

Key counting rules:

| Protocol | Has IPv4 layer? | Has ports? | Notes |
|----------|:---:|:---:|-------|
| TCP | Yes | Yes | Identified by IPv4 protocol number 6 |
| UDP | Yes | Yes | Identified by IPv4 protocol number 17 |
| ICMP | Yes | No | Identified by IPv4 protocol number 1; ICMPv6 is separate |
| ARP | No | No | Layer 2 only; operates below IP |
| IPv6 | No (it is not IPv4) | Varies | Excluded from all IP-related metrics |

The `protocol_ip_total` count should reflect all packets with an **IPv4** layer, which may include protocols beyond just TCP, UDP, and ICMP. A packet can match multiple protocol filters simultaneously (e.g., a TCP packet also counts toward IP total). Counting is not mutually exclusive across layers.

**Protocol counting implementation:** Each protocol counter (`protocol_tcp`, `protocol_udp`, `protocol_icmp`, `protocol_arp`) must check for its respective layer **independently** --- do not nest TCP/UDP/ICMP checks inside an `IP in packet` guard. While the table above shows that TCP/UDP/ICMP packets normally have an IPv4 layer, PCAP files with VLAN tags, tunneling, or unusual encapsulations may cause Scapy's `IP in packet` check to fail even when a valid TCP or UDP layer is present and correctly dissected. In Scapy terms, use `TCP in packet`, `UDP in packet`, `ICMP in packet`, and `ARP in packet` as independent top-level checks. The `protocol_ip_total` counter is the only one that should use `IP in packet`.

## Packet Lengths and Size Statistics

The "length" of a packet typically refers to the length of the entire captured frame as it appears in the PCAP, starting from the data-link layer. In Scapy, `len(packet)` returns this full frame length, including all headers and payload. Scapy is a standard Python library for PCAP analysis and is commonly pre-installed in analysis environments. Note that some other tools or libraries may report only the IP payload length or the TCP payload length, which are smaller --- the full frame length should be used consistently across all size and byte metrics (including PCR byte calculations).

When computing size statistics (total bytes, average, minimum, maximum), apply them over **all** packets in the capture, not just IP packets. Every packet in the PCAP contributes to size statistics, regardless of protocol.

## Time-Series Analysis: Bucketing Packets by Time

Packet timestamps in a PCAP are floating-point epoch values with sub-second precision. The capture duration is simply the difference between the latest and earliest timestamps.

To compute per-minute rates, each packet is assigned to a bucket by taking the floor of its time offset from the capture start, divided by 60 seconds. Concretely, the bucket index for a packet equals `floor((timestamp - start_time) / 60)`. This relative bucketing anchors all buckets to the beginning of the capture; using absolute epoch-based buckets (e.g., `floor(timestamp / 60)`) would produce different bucket boundaries since the capture start generally does not align to a minute boundary.

Each bucket accumulates a count of packets that fall within its 60-second window. The average, maximum, and minimum packets-per-minute are then computed over these bucket counts. The first and last buckets may represent partial minutes, but they are included in the statistics as full buckets.

## Shannon Entropy

Shannon entropy measures the randomness or uniformity of a distribution. For a set of observed values (e.g., source IP addresses across all IP packets, or destination ports across all TCP+UDP packets), the entropy is computed as the negative sum, over all distinct values where the probability is greater than zero, of each value's probability multiplied by its base-2 logarithm. In notation, `H(X) = -sum(p(x) * log2(p(x)))`, where `p(x)` is the fraction of occurrences of value `x` relative to the total count.

**Interpretation in network traffic:**

- **Low entropy** indicates concentration: traffic is dominated by a small number of values. For IP addresses, this means a few hosts generate most traffic. For ports, traffic is focused on a handful of services.
- **High entropy** indicates dispersion: values are spread across many distinct items more uniformly. Extremely high port entropy from a single source can indicate port scanning. High IP entropy can indicate distributed activity.
- **Maximum possible entropy** equals `log2(N)` where N is the number of distinct values. Entropy close to this maximum means near-uniform distribution.

When computing port entropy, the frequency distribution is built over **all** TCP and UDP packets together (not separately). Each packet contributes its source or destination port to the respective counter. The unique port counts are simply the number of distinct values observed in these counters.

When computing IP entropy, only packets with an IP layer contribute. The frequency distribution is built over source IPs (for `src_ip_entropy`) or destination IPs (for `dst_ip_entropy`) from all IP-layer packets.

## Directed Communication Graph

Modeling network traffic as a directed graph enables topological analysis. Each unique IP address becomes a node. Each unique (source_IP, destination_IP) pair becomes a directed edge. Multiple packets between the same pair still produce only one edge.

**Density** measures how connected the graph is relative to its maximum possible connectivity. It is computed as the number of edges divided by the product of the number of nodes and one less than the number of nodes: `density = num_edges / (num_nodes * (num_nodes - 1))`. This formula applies to directed graphs where self-loops are excluded. If there are fewer than 2 nodes, density is defined as 0.

**Degree metrics:**

- **Outdegree** of a node: the number of distinct destination IPs that this source IP communicates with. Max outdegree identifies the most prolific initiator --- a host contacting many different targets.
- **Indegree** of a node: the number of distinct source IPs that contact this destination IP. Max indegree identifies the most popular target --- a host receiving connections from many sources.

The node set includes every IP address that appears as either a source or a destination in any IP-layer packet. Do not restrict nodes to only sources or only destinations.

## Inter-Arrival Time (IAT) Analysis

Inter-arrival time is the time gap between consecutive packets when all packets are sorted by timestamp. For N packets sorted chronologically, there are N-1 inter-arrival intervals.

Key statistics:

- **IAT mean**: average of all inter-arrival intervals
- **IAT variance**: population variance (divide by N-1 intervals, not N-2) --- that is, use `sum((x - mean)^2) / count` rather than Bessel's correction
- **IAT coefficient of variation (CV)**: `standard_deviation / mean`. CV normalizes the spread relative to the mean, making it comparable across different traffic rates.

**Interpreting CV for traffic classification:**

- **CV below ~0.5**: traffic arrives at highly regular intervals. In network security, this regularity is a hallmark of automated or "robotic" communication --- particularly command-and-control (C2) beaconing, where malware phones home at fixed intervals.
- **CV near 1.0**: traffic exhibits moderate burstiness, typical of normal mixed-use network activity (web browsing, email, file transfers).
- **CV well above 1.0**: traffic is highly bursty, with clusters of rapid packets separated by quiet periods.

IAT analysis covers **all** packets in the capture, not filtered by protocol. Sort all packets by timestamp before computing intervals.

## Producer/Consumer Ratio (PCR)

The PCR classifies each IP address by whether it predominantly sends or receives data. For a given IP, `bytes_sent` is the total bytes of all packets where that IP is the source, and `bytes_recv` is the total bytes of all packets where it is the destination. The PCR is then computed as `(bytes_sent - bytes_recv) / (bytes_sent + bytes_recv)`.

PCR ranges from -1.0 (pure consumer, receives everything) to +1.0 (pure producer, sends everything). A PCR near 0 indicates balanced bidirectional communication.

Only IP-layer packets contribute to PCR computation. The packet length used is the full frame length (same as size statistics). IPs with zero total bytes (sent + received) are skipped entirely.

Classification thresholds use a dead zone around zero:

- **Producer**: PCR > +0.2 (sends substantially more than it receives)
- **Consumer**: PCR < -0.2 (receives substantially more than it sends)
- **Balanced**: -0.2 <= PCR <= +0.2 (roughly symmetric traffic)

## Network Flow Analysis

A network flow is defined by a 5-tuple key: (source_IP, destination_IP, source_port, destination_port, transport_protocol). Only TCP and UDP packets generate flows, since ICMP and ARP lack port numbers.

**Unique flows** is the count of distinct 5-tuple keys observed across all packets. A single flow may consist of many packets.

**Protocol-specific flows**: TCP flows and UDP flows are simply the subsets of unique flows filtered by the protocol field in the 5-tuple.

**Bidirectional flows**: A flow is bidirectional if its reverse 5-tuple also exists in the flow set. The reverse of `(src_ip, dst_ip, src_port, dst_port, proto)` is `(dst_ip, src_ip, dst_port, src_port, proto)`. When counting bidirectional flows, each pair of forward/reverse flows should be counted once, not twice. If you iterate over all flows and check for the reverse, each bidirectional pair will be found twice (once from each direction), so divide by 2.

## Traffic Classification: Detecting Anomalous Patterns

Network intrusion detection combines multiple computed metrics to identify specific attack patterns. No single metric is sufficient --- classification requires reasoning about combinations of indicators.

### Port Scanning

A port scan occurs when an attacker systematically probes many ports on a target to discover open services. Reliable detection requires multiple converging signals from a single source IP:

1. **High port entropy per source**: a scanner distributes probes roughly uniformly across many ports, producing high entropy in its destination port distribution. Normal clients repeatedly contact the same few service ports (80, 443, 22), producing low entropy.
2. **High SYN-only ratio**: scanners often use half-open (SYN) scans that send a SYN packet but never complete the handshake. A high fraction of SYN packets without corresponding ACKs indicates probing rather than legitimate connections.
3. **Large number of unique destination ports**: scanning implies contacting many distinct ports. Normal usage involves a small, repeated set of well-known ports.

A single indicator is not sufficient. A host may contact many ports over a long period through legitimate activity, but a scanner combines high entropy, high SYN-only rate, and high unique port count simultaneously.

### Denial of Service (DoS)

DoS attacks flood a target with traffic to exhaust resources. The primary signature is an extreme traffic rate spike relative to baseline activity. Compare the maximum packets-per-minute to the average packets-per-minute: if the ratio is extraordinarily large (indicating a sudden flood dwarfing normal activity), a DoS pattern may be present. Normal enterprise traffic shows some variability in rate, but the peaks and averages remain within a modest ratio of each other.

### Command-and-Control (C2) Beaconing

Beaconing occurs when compromised hosts communicate with a C2 server at regular, periodic intervals. The key indicator is **low inter-arrival time variance relative to the mean** --- specifically, a low coefficient of variation. Human-driven traffic is inherently bursty and irregular, producing higher CV values. Automated beaconing produces metronomic regularity with a CV substantially below what normal traffic exhibits.

## The DAPT2020 Dataset

The DAPT2020 (Distributed APT) dataset is a network traffic dataset designed for advanced persistent threat research. Its subsets may contain benign enterprise activity, attack traffic, or both. Common protocols can include substantial ARP traffic on local network segments, standard TCP/UDP application traffic, and smaller amounts of ICMP.

Do not infer a subset's label from the dataset name or from a single conspicuous statistic. Classify the supplied capture from the metrics computed from its packets. In particular, a high unique-port count can arise from ordinary ephemeral client ports; a port-scan conclusion requires converging evidence such as source-level fan-out, destination-port diversity, and connection-attempt behavior.
