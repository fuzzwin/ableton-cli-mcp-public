Plan frozen before implementation tests.

Unit checks: input bounds/types, stale-session and write gating, malformed requests,
MIDI note validation, batch preflight and partial failures, replay and ID collision,
track and parameter bounds, native ALS limits and read-only inspection.

Integration checks: actual TCP loopback server with an explicitly synthetic Live
object, authenticated framing, persistent connections, oversized input and shutdown;
installed CLI subprocess help/JSON/error paths; official MCP ClientSession handshake,
tool listing and calls over stdio, read-only versus write-enabled tool discovery.

Real backend gate: after installing and selecting the Remote Script, capture status,
track and device reads from Ableton Live 11.3.12 and a bounded read latency sample.
Existing music projects and transport are preserved. Live mutation and audio export
acceptance are not inferred from synthetic tests or read-only integration.

Initial planned inventory: test_contract.py (~15), test_transport.py (~6),
test_interfaces.py (~6), plus a separately invoked real-backend probe.
