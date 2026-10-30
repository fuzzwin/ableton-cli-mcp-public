# Ableton CLI + MCP

**Agent-ready music production · Silent rendering · Self-mixing & mastering · Reference-aware workflows · Local learning · Live progress**

A working local CLI and MCP connector for Ableton Live, with an optional file-based audio production harness. Connect a compatible assistant, describe your goal and let it call the supported tools. You can also use every workflow from a terminal.

**[Start with the user guide →](USER_GUIDE.md)** · [Capabilities & limits](docs/NATIVE-CAPABILITIES.md) · [Verification](docs/VERIFICATION.md)

## Capabilities at a glance

- **Inspect Ableton:** session state, tracks, parameters, MIDI clips and native `.als` files.
- **Mix bounced stems:** explicit gain, pan, filtering, compression and kick-keyed ducking, with optional bounded role balancing.
- **Master and compare:** measured loudness/estimated true peak, named profiles and level-matched A/B files.
- **Work from a reference:** selected passages, your mix goals and numerical comparisons.
- **Edit samples:** trim, reverse, fades and gain to new audio files.
- **Know your plugins:** macOS metadata index plus explicit single-plugin AU/VST3 file probes.
- **Remember useful results:** local measured evidence and your explicit feedback; no model training.
- **See progress:** actual backend stages, counts, elapsed time and warnings in a local dashboard.
- **Try original music:** two reproducible two-minute demo recipes with stems, editable MIDI and actual harness mix/master outputs.

## Quick start

Requires Git, Python 3.10+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/fuzzwin/ableton-cli-mcp-public.git
cd ableton-cli-mcp-public
uv sync --locked --extra audio
mkdir -p production-workspace
.venv/bin/cli-anything-ableton --help
```

Point your MCP client at `.venv/bin/ableton-mcp --workspace /absolute/path/to/production-workspace`. See [mcp-config.example.json](mcp-config.example.json) and replace its absolute-path placeholders. With a workspace, **20 tools** are exposed by default. No model or API key is bundled; your compatible client supplies the assistant.

Try asking:

> Analyze `mix.wav`, preserve my original and work silently. Then make one justified master version and explain the measurements and what still needs listening.

File workflows run with Live closed. For native inspection, install the bridge with `cli-anything-ableton --json bridge install`, then select **CLIAnything** in Live's Control Surface settings with Input/Output **None**. [Full setup](USER_GUIDE.md#3-connect-ableton-optional-for-file-workflows).

## Listen to the created songs

Both tracks are original, two minutes long and available as 24-bit stereo WAV downloads (about 32 MB each). These listening downloads are private; sign in to GitHub with repository access.

| Song | Style | Download |
| --- | --- | --- |
| **Horizon After Rain** | Spacious melodic house · 128 BPM | [Download WAV](https://github.com/fuzzwin/ableton-cli-mcp/releases/download/listening-demos-20261030/Horizon-After-Rain-Master.wav) |
| **Signal in the Concrete** | Broken beats, acid bass and big-beat energy · 136 BPM | [Download WAV](https://github.com/fuzzwin/ableton-cli-mcp/releases/download/listening-demos-20261030/Signal-in-the-Concrete-Master.wav) |

[Open the listening release](https://github.com/fuzzwin/ableton-cli-mcp/releases/tag/listening-demos-20261030) if a direct download does not open.

## Run the demos

```sh
.venv/bin/python scripts/demo_songs.py --workspace production-workspace --song all
.venv/bin/python scripts/proof_visual.py --workspace production-workspace --port 8788
```

Open http://127.0.0.1:8788 to observe supported mix/master jobs. Synthesis progress prints to the terminal. **Horizon After Rain** explores spacious melodic house; **Signal in the Concrete** moves from swung broken beats to acid/bass and big-beat energy. Both are exactly two minutes, with ten stems and original MIDI. The recipes use original procedural synthesis, with no commercial sample/VST dependency. Audio outputs remain local and are ignored by Git.

## Clear boundaries

Silent operation and read-only Live access are the defaults. Native mutations require opt-in on both sides; playback has a separate gate. Full native arrangement editing, instrument loading, recording, set saving and Live export are not implemented. The demo script is an authored example, not a general composition MCP endpoint.

Native read access was checked on macOS/Live 11.3.12. Automated mutation tests use synthetic Live objects. Windows, other Live versions and arbitrary plugins need their own validation. Numerical checks do not establish perceptual quality or artist similarity. There is no automatic web research, certified true-peak meter, model retraining or bundled scheduled agent.

## Open source and evidence

Apache-2.0. The CLI-Anything REPL skin retains its upstream license/attribution. This is an independent community implementation, not an Ableton product or upstream CLI-Anything release. [CLI-Anything](https://github.com/HKUDS/CLI-Anything) informed the harness method; [Proof Loop](https://github.com/fuzzwin/proof-loop-public) supplies bounded evidence checks.

This public repository begins with a reviewed source snapshot. Private history, configs, inventories, learning records and audio are excluded. See [verification](docs/VERIFICATION.md), [security](SECURITY.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
