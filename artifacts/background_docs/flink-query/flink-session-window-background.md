# Event-Time Sessions in Stream Processing

This document summarizes general stream-processing concepts. It does not describe a particular dataset, job identifier, source file, class, expected output, or test result.

## Event time and watermarks

Event time is the time recorded by the event, while processing time is when a system observes it. When timestamps arrive out of order, a watermark represents the engine's estimate that event time has advanced. Event-time windows normally finalize only when the watermark passes their end, subject to any allowed-lateness policy.

Timestamp units must be established from the source schema. Treating microseconds as milliseconds, or assigning timestamps from the wrong event field, changes both ordering and window membership.

## Keyed session windows

A session window groups events for one key while consecutive activity remains separated by less than a configured inactivity gap. A sufficiently long gap closes the current session and a later event starts another. Session windows are dynamic and may merge as out-of-order events arrive.

Key before applying a per-entity session window. Aggregate the events that semantically represent activity, and keep repeated activity records when the domain treats repeated attempts as distinct events. If a result is meaningful only after a separate lifecycle event, that completion stream must be joined or connected using the same stable key without discarding already accumulated session state.

## Flink implementation considerations

Flink programs need serializable record types with fields and constructors compatible with the selected API. Parsers should follow the published schema, tolerate optional fields deliberately, and reject malformed records without silently shifting column positions. Compressed text sources may be read through the filesystem APIs supported by the runtime rather than being fully unpacked in memory.

File sinks and batch-style test runs still rely on stream termination or bounded input so that windows, timers, and buffered output can complete. Use deterministic text formatting and avoid depending on record order unless the contract requires ordering.

## Validation

Test session behavior on activity just below, exactly at, and just above the inactivity boundary; on interleaved keys; and on out-of-order input. Separately verify timestamp units, repeated-event counting, lifecycle completion, output serialization, and successful compilation against the installed Flink version.
