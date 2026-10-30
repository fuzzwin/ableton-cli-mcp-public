# Observable production progress

1. Long production operations record real stage transitions in per-job, local
   snapshots: analysis, mix, master, sample edit, reference, master versions,
   plugin inventory/probe. Track simultaneous jobs separately. Source audio and
   pure preparation remain untouched. No speaker playback or native Live edits.
2. Show queued, current and completed stages, item counts when observed, start /
   update times, elapsed time, output references and terminal state. Stage counts
   are not a time percentage or ETA. Never simulate work or mark unreached stages
   complete. Errors mark the current stage failed and preserve prior observations.
   Silent/failed plugin probes and failed technical checks need attention.
3. Heartbeats show a job process is still present without fabricating stage
   progress. Missing fresh heartbeat means unconfirmed/interrupted, not success.
   Reading progress must not create state. Use bounded records/history and
   workspace-contained paths; reject traversal and escaping symlinks.
4. The read-only localhost viewer displays current production jobs prominently,
   keeps Proof Loop evidence separate, and updates without playback/action
   controls. Do not expose arbitrary files, tokens, source audio or full ledgers.
   Runtime job data remains ignored by Git.
5. CLI uses the same production API. MCP keeps CPU/file work off its event loop,
   allowing a read-only status tool while work runs. Native MCP notifications are
   optional to client progress-token support; share the same observed stage data.
   Observer/client notification failure must not corrupt the file operation.
6. Keep existing80cases and add lifecycle, failure, stale state, read-only status,
   concurrency, real workflow-stage and actual SDK notification tests. Verify
   real intermediate browser UI plus the final result. No claim that progress
   establishes auditory quality, cancellation support or formal acceptance.
