# Internal listen mode

`ableton_listen` builds a silent review packet from bounced audio. It helps an
assistant inspect what changed across a song before proposing another version.
This mode uses signal analysis. It has no perceptual audio model and cannot hear
or understand music as a human listener does. Creative approval stays pending.

Ask your assistant:

> Review the bounce internally without speaker playback. Inspect its section
> contrast, dynamics, stereo/mono balance and rhythm candidates. Use the dry lead
> and sub stems for pitch estimates. Explain timestamped evidence separately
> from musical hypotheses. Preserve the originals and make no automatic edits.

The assistant authors a workspace-relative JSON plan. Start with
[listen-plan.json](../examples/listen-plan.json), changing sections to match the
actual duration and removing any unavailable stems. A plan with only
`{"source":"mix.wav"}` works; it uses successive eight-second windows. A supplied
`reference` path enables level-normalized comparison metrics. Reference passages
should be prepared separately when the desired comparison is narrower than the
whole file. No artist reference is required.

```sh
.venv/bin/cli-anything-ableton --json --workspace production-workspace production listen listen-plan.json
```

MCP: `ableton_listen({"plan_path":"listen-plan.json"})`. Preparation supports
`task: "listen"`, with `source` pointing to the JSON plan. Reconnect an existing
MCP client to discover the new tool. A server without a workspace does not expose
this mode. The default workspace server now exposes 23 tools.

The packet contains source/stem/reference hashes, whole-file measurements,
timestamped RMS/crest/brightness/stereo observations, energy-rise candidates and
optional timing distances to a supplied sixteenth-note grid. BPM is an explicit
hint, not tempo detection. The grid begins at time zero, with 20 ms onset
resolution. Swing, pickups, syncopation and negative space can be intentional.
Brightness is a power-weighted centroid restricted to 0–4 kHz, not a full-band
perceptual timbre description. Stem RMS does not measure masking or perceived
loudness. Source-rate section measurements preserve exact silent passages.

Only explicitly declared monophonic lead/bass stems receive pitch diagnostics:
8 kHz autocorrelation over 128 ms frames, confidence, voiced coverage, pitch
range/classes and at most 128 estimated note spans. Polyphony, rich harmonics,
distortion, slides, reverb and short gates can cause misses and octave errors.
These estimates are neither a transcription nor a tuning verdict. Pitch classes
do not establish a key. No melody score or automatic quantization is provided.

Inputs use the existing WAV/AIFF/FLAC bounds: mono/stereo, 0.5–600 seconds and at
most 30 million frames. At most four aligned stems must match source sample rate
and frame count. Up to 24 named sections must be ordered, nonoverlapping, at
least 0.5 seconds and inside the source. Unknown fields, escaping paths and
nonfinite audio/numbers fail. Silent whole inputs are rejected; silent passages
inside a valid track remain reportable. Silence-only stems should be omitted.

Each invocation writes a new `renders/<unique>/review.json`, logs a measured
`review` event and emits observed progress stages. Use `ableton_progress` and
`ableton_recall` to retrieve status/evidence. Results are local context, not model
training or human feedback. Reuse a review while its input hashes and plan remain
unchanged. Only explicit human feedback should mark a version as preferred.

Measurements and proposed actions are separate. Proposed actions are hypotheses
that require a musical decision. This mode does not change a mix, load plugins,
contact a service, start Live transport or open an output device. A numerical
pass cannot tell whether a lead is exciting, a hook is memorable or a mix is
pleasing. A future perceptual backend would need separately verified capability;
none is silently assumed here.
