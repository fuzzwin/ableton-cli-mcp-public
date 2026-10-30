# Silent production harness v1 criteria

Freeze these criteria before implementing this extension. The initial 33-case
bridge contract remains unchanged and must also pass.

1. File-only audio paths never invoke a playback API or start Live transport.
   Production tools require an explicit workspace and reject traversal and symlinks
   escaping it. Inputs are preserved; every render uses a new output directory.
2. WAV/AIFF/FLAC audio is bounded, finite, mono/stereo, and long enough for gated
   loudness. Silence, corrupt data, multichannel and mismatched stems fail clearly.
   Reports contain content hashes, LUFS, approximate 4x true peak, clipping, stereo,
   low-band width, spectrum and time-window dynamics. They do not imply audition.
3. The mix renderer uses an explicit 1..24 stem plan: gain, pan, optional high pass,
   optional compressor, and kick-keyed bass ducking. No filename-driven artistic
   rebalance. It produces a headroom-controlled premaster and a measured master.
   The master uses linked gain control and a measured oversampled ceiling. At most
   two candidates may be evaluated; unsatisfied loudness is reported honestly.
4. Plugin discovery reads macOS system/user VST3/AU/VST2 bundle metadata without
   loading executables. Installed is not usable: actual offline probe evidence is
   specific to plugin metadata fingerprint, host, architecture and test stimulus.
   Explicit probes run in a bounded child process, write files only, and retain
   silent/failure outcomes. No bulk plugin loading, update or purchase.
5. Knowledge retrieval uses a versioned schema with source URL, authority, checked
   date, applicable version, tool/style tags, claim boundaries and optional artist
   examples. Sources are reference data, never execution instructions. Style
   retrieval works without an artist. No copied commercial recordings or preset
   collections and no invented artist settings or popularity rankings.
6. A local append-only evidence ledger records render outcomes and explicit user
   feedback with hashes. Retrieval distinguishes measured technical outcomes from
   subjective feedback and proposed corrections; no automatic model training or
   universal quality claim. Future reviews can reuse this evidence.
7. The CLI and official MCP expose the above only with an explicit workspace.
   Bridge-only compatibility is retained. Silent mode rejects play/clip launch
   before any backend call even if Live writes are enabled; playback needs an
   explicit opt-in. No host settings are silently modified.
8. A read-only localhost visual panel shows real pinned Proof Loop reports and
   acceptance limits. Retain tests, findings, bounded repair evidence and next-day
   handoff. Repository publication excludes tokens, audio, plugin binaries,
   user-specific runtime inventory and local learning records.

Limits: numerical analysis is not perceptual listening; file DSP is not native
Ableton export; 4x interpolation is an estimate, not certified BS.1770 true-peak
metering; technical success is not creative acceptance. Tests and requirements
share an OS account and are not independently held.
