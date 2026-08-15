# Reproducible dependency auditing

Vulnerability results depend on both the resolved dependency graph and the
advisory snapshot used for the scan. Keep those inputs internally consistent
for a run and retain enough provenance to explain which snapshot produced the
report. In an offline environment, use the locally available data rather than
silently mixing it with partial network results.

Resolve exact installed versions, including transitive dependencies, before
filtering findings by the requested severity. Filtering findings and projecting
report columns are separate operations.

Aliases can connect several advisory records that describe related issues, but
fields from different records are not interchangeable. For each reported
finding, take its identifier, severity, score, remediation, title, and primary
reference from one coherent source record. Preserve missing values explicitly
and use deterministic duplicate handling and row ordering so the output can be
reproduced.
