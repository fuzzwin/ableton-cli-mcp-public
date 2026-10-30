# Capability and execution boundaries

The default workspace server exposes 20 tools. The six native readers are `ableton_status`, `ableton_capabilities`, `ableton_tracks`, `ableton_parameters`, `ableton_clip`, and `ableton_inspect_set`. Fourteen additional tools cover preparation, analysis, mix, master, plugin inventory/probe, knowledge, feedback/recall, methods, reference briefs, sample editing, master versions and progress. A workspace must already exist. Tool discovery does not prove a bridge is connected.

Read-only native inspection was observed on macOS with Live 11.3.12. Automated Live tests use synthetic objects; they do not qualify native mutations on every Live version. Files are separately processed by Python DSP; no Live audio export is called.

## Optional edits

The implemented `ableton_apply` schema supports tempo, play/stop, MIDI/audio track creation, rename/mute/solo/volume/pan, device parameter values, MIDI Session clips with notes, and occupied clip launch/stop. This adds one tool when enabled. Native arrangement editing, rack traversal, loading effects/instruments, recording, delete, set saving and native export are not implemented.

To deliberately enable mutations on both sides:

```sh
.venv/bin/cli-anything-ableton --json bridge install --replace --allow-writes
# Reselect the script in Live (None, then CLIAnything), or save and restart Live.
.venv/bin/ableton-mcp --allow-writes --workspace /absolute/path/to/workspace
```

Inspect status and targets first. Both sides must permit writes; the server alone cannot enable them. Existing bridge installations are backed up by the installer. Playback/clip launch also requires `--allow-playback` on the client server/CLI path. Leave it absent for silent work. This guide does not recommend enabling playback to test the connector.

Apply uses the current session ID, validates existing targets, and bounds batches to 32 operations / 4096 total notes. A single undo group is not a guaranteed automatic rollback. Create a track, re-inspect, then create its clip in another call. Human track-order edits between calls still matter. Request IDs are a process-local replay guard; never automatically retry an uncertain write.

Inspect parameter bounds before edits. Track volume uses Live's linear 0..1 value, not decibels; clip timing uses quarter-note beats. Dense note reads can be costly because Live returns a whole clip before pagination. No hard realtime deadline is guaranteed.

## Local execution

The Remote Script uses Live's main-thread update callback and a token-authenticated loopback listener. The MCP server uses official SDK stdio. The optional visual panel is a separate read-only loopback HTTP process. Do not expose either listener remotely. Plugin subprocess time/CPU/log limits are not an OS sandbox.

The demo recipes are authored original procedural synthesis outside Live. They produce WAV stems and standard MIDI, then call the supported mix/master pipeline. They neither load native VST instruments nor claim full-song composition is implemented by MCP.
