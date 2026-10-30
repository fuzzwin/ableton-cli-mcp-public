# Public release verification

Current source 0.7.0 adds installed-plugin context and bounded sound design; its scoped suite contains 114 cases (100 prior cases plus 14 sound-design cases). See docs/PLUGIN-SOUND-DESIGN.md for execution limits. Earlier 0.6.0 release reports remain historical evidence for their own hashes; they do not cover changed source. The separate actual musical edit is a private file artifact, not perceptual or native Live acceptance.


Version 0.6.0 is a fresh public source snapshot. Private Git history, identity-bearing local reports/configs, audio, inventories, feedback and runtime jobs are excluded. Original source is Apache-2.0, with CLI-Anything provenance/license retained.

The automated suite covers native schema/gating with synthetic Live objects, real local TCP/stdio/official MCP clients, constrained file DSP, source preservation, reference/sample/master variants, preparation and observed progress. Release checks additionally inspect the public export allowlist/manifest, portable guide links, MIDI note timing and non-overwrite behavior.

The two real two-minute demo runs use ten original procedural stems each. They pass through Production.mix, including final WAV decoding, hashes, LUFS, estimated 4x true peak, clipping and source preservation. See [sanitized demo measurements](DEMO-RESULTS.json). Audio and original MIDI are local run products, not public repository content. No artist recordings, commercial samples, plugin binaries or voices are used.

A fresh independent reviewer checks release content, claims and demo code. A real pinned Proof Loop run uses revision `198a695186055eaaca6b5150f13521a90f29be79`, separate command-json verification/validation checks and frozen test identities. Same-account source/tests do not establish independent custody. `acceptance: not_accepted` remains the formal result even if scoped checks pass. Public reports are sanitized before publication; private source evidence is not copied here.

Native read-only observations were made on macOS with Live 11.3.12. File/synthetic CI runs on Linux with Python 3.13. Those observations do not establish Windows support, native mutation acceptance, arbitrary plugin compatibility, perceptual similarity or commercial music quality. No speaker playback or model training is part of these checks.

To repeat local checks:

```sh
uv sync --locked --extra audio
uv run --locked --extra audio python -W error::ResourceWarning -m unittest discover -s acceptance -v
```

To run Proof Loop, obtain the pinned public source separately, then:

```sh
.venv/bin/python scripts/run_proof_visual.py --proof-loop /path/to/proof-loop-public/proofloop --run-id your-unique-run-id
```

Reports are newly generated from that checkout; input hashes and timestamps determine their scope. No historical report is a guarantee about changed source. See PUBLIC-MANIFEST.json in the public checkout for the initial exported file hashes; later release reports are identified separately.
