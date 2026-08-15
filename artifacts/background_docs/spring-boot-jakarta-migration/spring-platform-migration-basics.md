# Spring platform migration basics

A major Java and Spring upgrade is safest as a dependency-consistent migration
rather than a sequence of isolated text replacements. Establish the target JDK
and framework dependency-management baseline first, remove obsolete version
overrides, and use compilation and tests to discover incompatible APIs.

Modern Jakarta EE APIs use `jakarta.*` namespaces. Migrate imports together
with the libraries and annotations that define their runtime behavior. Check
persistence mappings against the current ORM semantics, validation constraints
against the current validation provider, and serialization behavior at REST
boundaries.

Security migrations should preserve authorization intent while adopting the
current configuration style, request matching APIs, password handling, and
filter-chain lifecycle. HTTP-client migrations should preserve URI expansion,
headers, authentication, error handling, request bodies, and response typing.

Work in short compile-test cycles. Search the whole source and build tree for
legacy namespaces and deprecated APIs, then run a clean build so stale classes
cannot hide missing dependencies. Validate both expected success paths and
authentication, authorization, validation, persistence, and external-call
failure paths.
