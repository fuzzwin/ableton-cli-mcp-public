# Visible production stages

The localhost panel now shows production activity above the Proof Loop results.
Open http://127.0.0.1:8788 after starting the read-only viewer:

```sh
.venv/bin/python scripts/proof_visual.py --port 8788 --workspace production-workspace
```

Analysis, mixing, mastering, sample edits, reference briefs, master-version
experiments and plugin inventory/probes record observed stages. For example a mix
shows input checks, stem processing, mastering, writing, saved-bounce checks and
evidence recording. Item counts are recorded when known. These are work-stage
counts, not elapsed-time percentages or an estimated completion time.

The display follows new active work automatically. Select a previous job to pin
it, or choose Follow newest activity to resume following. Concurrent jobs have
independent IDs and records. Current, completed and unreached stages are distinct.
Failures preserve the last observed stage; technical target misses and silent or
failed plugin tests finish as needs_attention. Completion never means auditory
or creative acceptance. Pure preparation and short guide reads create no jobs.

A background heartbeat updates liveness every five seconds without advancing a
stage or inventing an activity event. Twenty seconds without a heartbeat becomes
unconfirmed, including after a process disappears. Invalid/nonfinite/inconsistent
records cannot claim liveness or success. A polling connection failure also marks
the displayed state unconfirmed. Terminal records remain historical observations.

Every tracked API/CLI result includes progress_job_id. Read one or recent jobs:

```sh
.venv/bin/cli-anything-ableton --json --workspace production-workspace production progress
```

The MCP tool is ableton_progress. Clients requesting native progress notifications
receive the same observed stages and counts. Notification sequence numbers count
events, not time percentages. MCP file/DSP work runs in a dedicated pool with at
most two workers per server, keeping status queries responsive. Requests waiting
for a worker get a native queued notification; their stage record begins when
the worker starts. Separate CLI/server processes do not share that concurrency cap.
Notification transport failures do not change the file operation's result.

The panel is read-only and binds 127.0.0.1. It serves only the known viewer/API
endpoints; it has no playback, restart or cancellation controls. Runtime snapshots
are workspace-contained .ableton-harness/jobs records, ignored by Git. Existing
audio/bridge write gates remain unchanged. Failed operations may leave new partial
files; inspect the last confirmed stage and outputs before repeating work.

Verification: fourteen progress cases cover stage order, failures, incomplete
observations, heartbeat staleness, concurrency, read-only/path checks, corrupt
records, observer failure, actual API workflows and actual SDK notifications/status.
A fresh independent reviewer found UI-follow and record-validation gaps; both were
repaired in one bounded round and independently rechecked. The two-worker limit
also has a responsiveness check. The 0.6.0 release adds public export/guide/MIDI checks; see docs/VERIFICATION.md for the release scope.

A prior local browser check observed automatic job following, item updates,
pinning, a warning outcome and unchanged source hashes. The public two-minute
demo run adds real mix/master job evidence without speaker playback; see
[demo measurements](DEMO-RESULTS.json). Historical observations do not establish
current liveness or creative acceptance.

The viewer observes supported backend operations, not private agent reasoning or
all possible third-party work. Stage visibility does not establish listening,
universal reliability, cancellation support or formal Proof Loop acceptance.
Native SDK behavior was checked against installed 1.30.0 and its
[source](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/fastmcp/server.py).
