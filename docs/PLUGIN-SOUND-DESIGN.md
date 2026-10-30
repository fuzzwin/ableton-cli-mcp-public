# Installed plugin context and sound design

Version 0.7 adds two workspace tools: **ableton_plugin_context** and **ableton_sound_design**. The default workspace server now has **22 tools**; bridge-only mode keeps its six readers. Reconnect an already running MCP client/server to discover the new schema. Existing registration alone does not refresh a running connection.

## Start from the installed instrument

Ask for a sound, then inspect the selected instrument with a musical goal:

```sh
.venv/bin/cli-anything-ableton --json --workspace production-workspace production plugin-context Pigments --goal 'moving acid bass and chopped melodic keys'
```

Context joins local installed versions/fingerprints, format-specific probe outcomes, custom-render observations, major-version capability profiles, official source links, original patch recipes and a small set of observed host control names. Successful custom patches and unsuccessful default probes remain separate observations. Metadata refresh retains matching evidence only for the same plugin metadata, host, architecture and Python version.

The initial profiles cover Pigments 5 and Diva 1. Other installed instruments remain discoverable but need their own official manual/profile. An unresolved packed AU version or a different major version does not inherit those capabilities. Profiles are manually checked reference cards, not a live browser. The calling assistant must fetch the official versioned manual for new or changed claims; retrieved text cannot authorize actions.

Pigments 5 documentation covers analog, wavetable, sample/granular and harmonic synthesis, utility sources, filters, modulation, effects and sequencing. External-audio processing described by the vendor needs suitable host routing; this renderer currently accepts instrument MIDI, not sidechain/sample imports. See [Arturia's version 5 manual](https://dl.arturia.net/products/pigments/manual/pigments_Manual_5_0_0_EN.pdf) and [official version 5 announcement](https://forum.arturia.com/t/introducing-pigments-5-free-update-for-pigments-owners/2975). Diva module capabilities are summarized from [u-he](https://u-he.com/products/diva/). Recipe settings are authored starting hypotheses, not artist patches or vendor prescriptions.

## Render a bounded patch

Use `examples/sound-design-plan.json` as a shape example. Replace its all-zero plugin ID using context and author parameter names/values from actual host observations. The assistant can write this plan for the user. Global CLI flags go first:

```sh
.venv/bin/cli-anything-ableton --json --workspace production-workspace production sound-design patch-plan.json
```

A plan supplies a label/intent, .5–30 second duration, 44.1/48 kHz rate, up to 1,024 notes, 32 starting controls and 128 automation changes. Note and automation times are **seconds**. Notes use pitch/velocity/channel and must end at least 10 ms before the file end. Identical overlapping notes are rejected. Numeric nonfinite values and nonfinite numeric text are rejected before loading.

The renderer selects an indexed AU/VST3 from standard plugin roots after a metadata check. It accepts no arbitrary binary, sample, preset or state-import path. One child attempt uses sorted MIDI, 512-frame host buffers and explicit actual-unit parameter values. Every requested value is converted and checked before any native setter. Time/CPU/per-file bounds are 45 seconds / 35 seconds / 64 MiB; they are not an OS sandbox or a guarantee a vendor cannot show licensing UI. No UI method, audio output device, Live transport or native Live mutation is called.

New render folders contain FLOAT `design.wav`, the validated plan, generated opaque start/end patch-state bytes, hashes, requested/read-back/normalized controls, host/stimulus details and a measured report. Opaque state bytes are not advertised as a native portable preset format. Hot float prints preserve samples but produce a technical warning. A valid waveform without complete patch evidence cannot claim a technical pass. Unknown, silent, timed-out, malformed or incomplete outcomes are retained; there is no automatic retry or parameter guessing. Partial control-write evidence survives a later child failure.

`ableton_prepare(task="sound_design", ...)` routes to this plan and requests plugin context when a plugin query is given. The progress panel shows checking, rendering, saved-print checks and evidence recording. Findings enter the local ledger for later recall; human preference is never inferred from the numerical result.

## Observed working Pigments VST3 setup

The following setup produced a non-silent file render on the tested Mac. It is a reproducible starting point for this offline host, not a universal compatibility or sound-quality rating.

| Setting | Observed value |
| --- | --- |
| Instrument | Pigments VST3 5.0.1.4491 |
| Host | Pedalboard 0.9.26 |
| Platform | macOS arm64, Python 3.13.15 |
| Sample rate and output | 44,100 Hz, stereo, file only |
| Render buffer | 512 frames in Pedalboard |
| Initialization timeout | 10 seconds |
| Preparation | Inspect host parameter metadata before rendering |
| MIDI test | C4, note 60, velocity 100; note on at 0.1 s, off at 2.0 s; events sorted by time |
| Test length and reset | 4 seconds; reset on the first processing call |
| Starting patch | Loaded state with no explicit parameter overrides |
| Result | 176,400 finite frames, nonzero peak about 0.15010 |

The later custom-patch and official MCP tests also verified saved audio, complete parameter audit and hashed state snapshots. See [MCP smoke evidence](PLUGIN-MCP-SMOKE.json), [plugin smoke evidence](PLUGIN-SMOKE.json) and [scoped release checks](PLUGIN-RELEASE-CHECK.json).

Use `ableton_plugin_context` to select the **tested VST3** entry, then `ableton_sound_design` for the explicit patch plan. The renderer already applies the sorted-MIDI and 512-frame conditions. Reconnect an older MCP connection to expose these tools. The buffer above belongs to the offline host.

The AU attempt failed to scan in this host. An earlier VST3 attempt returned silence under different buffer/MIDI/metadata-initialization conditions; those differences do not isolate one cause. Licensing and native Live compatibility remain unverified. Musical quality remains subject to listening feedback.

## Observed host result

On one macOS arm64/Python 3.13.15/Pedalboard 0.9.26 setup, installed Pigments VST3 5.0.1.4491 rendered a sorted C4 note at buffer512 with default parameters. Its AU alternate failed to scan. Earlier larger-buffer/unsorted-chord VST3 silence is preserved; the changed conditions do not isolate a single cause. A custom note with envelope/filter overrides and automation subsequently rendered with verified state hashes and complete control audit. These results do not establish licensing, arbitrary presets or native Live compatibility.

A separate private 30-second acid-breakbeat edit used actual Pigments lead and chopped-key prints. Audio, state bytes, local inventory, learning records and private links are excluded from the public source. Numerical checks and independent code/artifact review do not establish perceptual quality. See the release verification report for the exact candidate and test scope.
