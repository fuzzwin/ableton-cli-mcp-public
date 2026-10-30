# Ableton CLI + MCP — user guide

**Agent-ready music tools. Silent rendering. Self-mixing and mastering. Reference-aware analysis. Local learning. Live progress.**

Describe the result you want in a compatible MCP assistant, or use the same tools from a terminal. Inspect an Ableton set, process bounced stems, make master versions and keep a useful history of what worked. Your original audio stays intact.

## What you can do today

| Capability | What it actually does |
| --- | --- |
| **Natural-language workflow** | Your MCP assistant turns your request into supported tool calls; `ableton_prepare` supplies a compact plan and missing-input checks. No model/API key is bundled. |
| **Ableton awareness** | Read session tempo, tracks, devices, parameters and MIDI clips through a local Remote Script; inspect `.als` files without opening Live. |
| **Self-mixing** | Render an explicit plan for up to 24 aligned stems: gain, pan, high-pass, compression and kick-keyed ducking. Optional role balance is bounded to ±3 dB. |
| **Mastering and A/B versions** | Render new masters with linked limiting, measured loudness/estimated true peak, named density profiles and level-matched comparison copies. |
| **Reference-aware decisions** | Compare selected passages and save your notes about bass, width, dynamics or tonal balance. A reference is guidance; its audio is not copied into your music. |
| **Internal listen mode** | Review bounced sections, rhythm candidates and pitch estimates from declared monophonic stems; keep measured evidence separate from musical hypotheses. This is silent signal analysis, not perceptual hearing. |
| **Sample editing** | Trim, reverse, fade and change gain into a new WAV, including short one-shots. |
| **Plugin context** | Index macOS AU/VST/VST3 metadata; explicitly probe one selected AU/VST3 in a file-only host. Installed, tested and usable in Live are different states. |
| **Local learning** | Recall measured results and your explicit feedback from a local evidence ledger. This is useful memory, not model training. |
| **Visual progress** | See actual stages, item counts, elapsed time, warnings and recent jobs in a localhost panel; compatible clients can receive MCP progress notifications. |
| **Original demo recipes** | Generate two complete two-minute arrangements, ten aligned stems per song and editable standard MIDI using original procedural synthesis. These are example scripts, not a general composition endpoint. |

**Ease of use:** install once, select a workspace, connect your MCP client, then describe your goal. File workflows work with Ableton closed. Live inspection requires the bridge. No speakers are used by default.

## 1. Install

You need Git, Python 3.10+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). The locked macOS/Linux checks use Python 3.13. Native Live checks were made on macOS with Live 11.3.12; Windows and other Live releases need their own validation. Plugin discovery/probing is macOS-focused.

```sh
git clone https://github.com/fuzzwin/ableton-cli-mcp-public.git
cd ableton-cli-mcp-public
uv sync --locked --extra audio
mkdir -p production-workspace
.venv/bin/cli-anything-ableton --help
```

The `audio` extra includes the file-analysis/render dependencies. This project is source-installed; do not assume a package of this name exists on PyPI. Ableton and commercial plugins are separately installed/licensed products.

## 2. Connect an MCP client

Add this server to your client's MCP configuration, replacing **both absolute paths**. Clients vary in configuration format and progress/prompt support.

```json
{
  "mcpServers": {
    "ableton-production": {
      "command": "/ABSOLUTE/PATH/ableton-cli-mcp-public/.venv/bin/ableton-mcp",
      "args": ["--workspace", "/ABSOLUTE/PATH/ableton-cli-mcp-public/production-workspace"]
    }
  }
}
```

Restart/reload the client if required. With a workspace there are **23 tools** by default: six native readers plus seventeen production/preparation/progress tools. Without a workspace only the six readers are exposed. File tools do not need a bridge connection or Live running.

Try:

> Analyze `mix.wav` inside the workspace. Check loudness, clipping, estimated true peak, mono compatibility and low-end width. Work silently and explain which decisions still need listening.

Copy your audio into the workspace first. Tool paths are relative to it, not arbitrary paths elsewhere on your computer.

For a timestamped internal review, ask: “Review `mix.wav` silently, using the dry
lead and sub stems for melody diagnostics. Explain observations separately from
proposed edits.” Your assistant can author [a listen plan](examples/listen-plan.json)
and call `ableton_listen`. See [the mode's capabilities and limits](docs/INTERNAL-LISTEN.md).

For a multi-step task:

> Use the Ableton harness to make a warm, spacious melodic-house mix from `mix-plan.json`. Load only relevant methods, plugin evidence and past feedback. Preserve originals and work silently. Use a supplied reference only for the passage and qualities I specify. Make one justified version, bounce it, check the output and compare at matched loudness. Keep versions and report changes, measurements and what still needs listening. Ask only for essential missing information.

A compatible client may also offer the selectable `ableton_workflow` prompt. Prompt selection is client-controlled; it is not a hidden automatic hook. Your assistant may author JSON plans for you; you do not have to write them by hand.

## 3. Connect Ableton (optional for file workflows)

Save your work. Install the Remote Script:

```sh
.venv/bin/cli-anything-ableton --json bridge install
```

In Live's Preferences/Settings → Link/Tempo/MIDI, choose **CLIAnything** in an unused Control Surface slot, with **Input: None** and **Output: None**. Save and restart Live if it is not listed. If your User Library is elsewhere, use `bridge install --help` to select it.

```sh
.venv/bin/cli-anything-ableton --json status
.venv/bin/cli-anything-ableton --json tracks --limit 16
.venv/bin/cli-anything-ableton --json parameters 0 0
.venv/bin/cli-anything-ableton --json set inspect /absolute/path/Song.als
```

Indices start at zero. `--json` goes **before** the command. The bridge binds to `127.0.0.1`, authenticates requests and stores a private local token. Never upload `bridge.json` or paste its token into an MCP config.

Native editing is opt-in on both bridge and server. Tempo, track state, device parameter values and MIDI Session clips have mutation implementations; the public automated checks use synthetic Live objects. A real read-only connection does not establish native mutation acceptance. See [native capabilities and limits](docs/NATIVE-CAPABILITIES.md) before enabling it. Playback additionally needs its own opt-in.

## 4. Mix stems and master a bounce

Put aligned mono/stereo WAV, AIFF or FLAC stems in `production-workspace/stems`. They must share the sample rate/frame count, be 0.5–600 seconds each and within the documented frame/work budget. Copy [the example plan](examples/stem-plan.json) into the workspace as `mix-plan.json` and edit paths or have your assistant do it.

```sh
.venv/bin/cli-anything-ableton --json --workspace production-workspace production mix mix-plan.json
.venv/bin/cli-anything-ableton --json --workspace production-workspace production analyze mix.wav
.venv/bin/cli-anything-ableton --json --workspace production-workspace production master mix.wav
```

Each render gets a unique `renders/<run>/` folder with audio and a JSON report. A mix writes both `premaster.wav` and `master.wav`. The default −12 LUFS / −1 dBTP target is a starting point, not a mandatory platform or genre standard. Target misses and excessive limiter reduction stay visible.

For alternatives, use [master-versions-plan.json](examples/master-versions-plan.json). Dynamic, balanced and dense profiles change target/timing/budget. Comparison WAVs share loudness so louder is less likely to be mistaken for better.

## 5. Give it a reference or edit a sample

Copy a legally available reference into your local workspace. Say **which seconds** matter and **what you want**: for example, “0:45–1:05, the bass weight and restrained high end.” Your own mix may use a different passage. Use [reference-plan.json](examples/reference-plan.json).

```sh
.venv/bin/cli-anything-ableton --json --workspace production-workspace production reference reference-plan.json
.venv/bin/cli-anything-ableton --json --workspace production-workspace production sample-edit sample-edit-plan.json
.venv/bin/cli-anything-ableton --json --workspace production-workspace production methods 'effects depth'
```

Reference comparisons are numerical diagnostics, not a perceptual similarity score. Artist names can be useful examples, but no particular artist is mandatory. The bundled source cards link to guides; the connector does not automatically browse the web or identify a recording's exact gear/presets.

## 6. Make the two original demos

From the repository root, with an existing workspace:

```sh
.venv/bin/python scripts/demo_songs.py --workspace production-workspace --song all
```

| Recipe | Direction | Length / tempo |
| --- | --- | --- |
| `horizon` — **Horizon After Rain** | Spacious melodic house, evolving chords, plucked hook, deep mono sub and a long build. | 2:00 / 128 BPM |
| `pulse` — **Signal in the Concrete** | Chopped synth gestures, swung broken beats, halftime bass, acid movement and big-beat energy. | 2:00 / 136 BPM |

Each unique song folder contains ten full-length stems, a section map, editable `.mid`, a mix plan and `demo-result.json`. The latter points to the actual harness premaster/master render. Standard MIDI preserves notes, not synthesizer patches. Drag stems into Live at the named tempo and choose instruments for MIDI if you want to re-sound it.

There are no artist recordings, copied hooks, vocals, sample packs, commercial VSTs or Live set templates in these recipes. Printed effects and ducking are in the audio. They are authored synthesis examples, not automatic “make any hit” or finished native `.als` generation. Use `--compose-only` to render stems/MIDI first, then call the CLI/MCP mix tool yourself.


## 7. Watch progress and keep useful feedback

```sh
.venv/bin/python scripts/proof_visual.py --workspace production-workspace --port 8788
```

Open **http://127.0.0.1:8788** while a supported production operation runs. The panel follows new jobs; select a previous one to pin it. Queued/running/completed/failed/needs-attention/unconfirmed are distinct. A heartbeat means the worker is alive, not that another stage finished. No invented ETA or percent is displayed.

The example script's synthesis prints its instrument count to the terminal. The panel tracks the subsequent supported mix/master stages; it does not yet visualize the synthesis stage. Stop the viewer with Ctrl-C. It has no playback or cancel button. Treat any other local process able to read this port as inside your local trust boundary.

Tell your assistant “I prefer the dynamic version; the hats are too bright,” and ask it to attach that feedback to the correct event. Future recall can use that preference. No preference is inferred from a numerical pass. There is no bundled scheduled service; recurring reviews must be configured explicitly by the user.

For a reusable map of what worked, failed and remains unproven, use the
[evidence learning agent workflow](docs/LEARNING-AGENT.md). `ableton_prepare`
with `task: "learn"` now retrieves learning-map context. Your client runs the
selected worker; the connector does not select a model or retrain it.

## Troubleshooting and honest boundaries

| Symptom | Next step |
| --- | --- |
| Bridge disconnected | Check Live is open and CLIAnything selected; reselect after a script update. Save before restarting. |
| No production tools | Add `--workspace` with an existing directory, then reload the MCP client. |
| File/path rejected | Copy inputs into the workspace; use relative paths. Escaping symlinks and traversal are rejected. |
| Plugin is indexed but probe is silent | Check the exact plugin/host/preset/architecture/licensing combination. Do not treat installation as usability. Explicit probes may show vendor licensing UI. |
| Master needs attention | Read target and limiter-budget results. Try a more dynamic target; do not repeatedly push loudness to hide a warning. |
| Panel says unconfirmed | Restore its connection or inspect the worker/heartbeat; do not assume completion. |

No native arrangement editing, recording, plugin loading inside Live, set saving or Live audio export is implemented. Native warping and slicing-to-MIDI remain manual. File analysis does not hear music or certify commercial quality. Estimated 4× true peak is not a certified meter. Plugin child limits are not an OS sandbox. Existing native mutation batches use an undo group, not guaranteed automatic rollback.

## Verification and credits

Run `uv run --locked --extra audio python -m unittest discover -s acceptance -v`. Synthetic unit/integration checks are separate from hardware/plugin compatibility and your creative listening verdict. Proof Loop check reports preserve `acceptance: not_accepted`; read [verification](docs/VERIFICATION.md).

Independent community implementation; not endorsed by Ableton or the named artists. The harness method and REPL skin come from [CLI-Anything](https://github.com/HKUDS/CLI-Anything); evidence checks use [Proof Loop](https://github.com/fuzzwin/proof-loop-public). Original code is Apache-2.0; see [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).

## 8. Design sounds with an installed plugin

Start with `ableton_plugin_context` and the musical goal, then fetch the linked official manual for that installed major version when needed. The initial profiles cover Pigments 5 and Diva 1; unknown instruments need their own verified source. Author `examples/sound-design-plan.json` using the returned plugin ID and observed controls, then use `ableton_sound_design` to print a new file. Notes and automation use seconds; renders are limited to 30 seconds. No user-written JSON is required when the assistant can author the plan. See [plugin sound design](docs/PLUGIN-SOUND-DESIGN.md) for CLI commands, patch evidence and host limits.

The assistant researches official sources; the context backend does not automatically search the web. New render outcomes are retained for recall. A successful waveform, complete patch audit, licensing and native Live support remain separate. Reconnect an existing MCP client to discover the new tools.

The successful Pigments VST3 setup is recorded in the [verified setup table](docs/PLUGIN-SOUND-DESIGN.md#observed-working-pigments-vst3-setup), including version, host, buffer, MIDI stimulus and failure boundaries. Use that technical evidence as the starting point; keep your listening verdict separate.

## Bass, drums and effects context

Ask for a specific musical problem: “make space between kick and bass,” “a less crowded snare/clap,” “swung hats with choke,” “use a loop without losing transients,” or “phrase-end delay with a clear dry hook.” The connector can retrieve26 source cards and15 suggested methods through `ableton_knowledge` and `ableton_methods`. Each result names its sources, limitations and which steps need native/manual work.

Full-song preparation defaults to two minutes with contrasting sections; an explicit duration overrides it. Describe the arc and the focal musical role. The tool can analyze and process authored bounced files, but this default does not add an arbitrary song-generation or native export endpoint. Plugin and sample availability must be verified locally. Musical quality remains a listening decision.
