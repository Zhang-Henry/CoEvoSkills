# General Background on HTTP-Aware Suricata Inspection

Suricata signatures combine a traffic-selection header with an option list. For application protocols such as HTTP, semantic inspection is more reliable than matching arbitrary packet bytes because the engine can parse and reassemble a transaction that spans multiple TCP segments.

## HTTP buffers

Suricata exposes parsed request components through HTTP-specific buffers, including the method, URI, headers, and request body. A condition must be evaluated in the buffer that represents the intended protocol element. Conditions placed in one signature are normally conjunctive, so every required observation must hold for the same transaction.

HTTP syntax has normalization rules. Header names are case-insensitive, request targets can contain more than a path, and body representation depends on content type. A rule author should distinguish semantic requirements from incidental capitalization, whitespace, packet boundaries, or capture layout.

## Pattern and rule quality

Literal and regular-expression matching have different precision and performance characteristics. Character sets, repetition, anchoring, and normalization should be chosen from the public detection requirement. A substring that resembles a field is not necessarily the field itself, and a prefix that satisfies a pattern is not necessarily the complete value.

Rules should be syntax-checked and replayed offline against representative positive and negative traffic. Useful negative cases change one requirement at a time. Structured alert logs can then confirm the signature identifier and reveal false positives or missed transactions.

Concrete literals, lengths, field structure, capture contents, and the final signature must be obtained from the public instruction and runtime files. They do not belong in reusable background documentation.
