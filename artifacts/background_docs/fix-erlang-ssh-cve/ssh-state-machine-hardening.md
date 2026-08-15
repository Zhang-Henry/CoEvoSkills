# Hardening an SSH protocol state machine

SSH separates transport negotiation, user authentication, and the connection
protocol.  Messages that can create channels, request services, or trigger
application behavior must not be dispatched before the connection has reached
an authenticated state.  Packet parsing alone is not authorization.

In a message-driven Erlang server, trace each relevant message from decoding
through state dispatch and identify the narrowest common authorization
boundary.  Reject or disconnect on capability-bearing messages received in an
invalid state while preserving valid authenticated behavior and ordinary
protocol error handling.  Avoid fixes that depend only on one packet ordering
or one application command.

Keep the patch small and state-oriented.  Check Erlang clause ordering,
pattern matching, return-state transitions, and syntax, and use existing tests
or compilation checks to confirm that normal authenticated flows remain
reachable and unauthenticated capability requests cannot reach execution.

