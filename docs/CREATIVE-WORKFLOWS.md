# Creative methods and reference-driven experiments

User goal: learn methods for editing, sampling, effects, mix decisions, style
exploration and mastering; accept a supplied example of the desired mix sound.
This extension builds practical file workflows while keeping native capabilities
and subjective judgments explicit.

Primary sources checked 30 October 2026 are indexed with version applicability:
Ableton Live 11 clip/warp, arrangement, instrument and effect manuals; Ableton's
Making Music creative-strategy index; FabFilter's limiter output/comparison help.
The seven workflow cards are original suggested methods. Source links document
underlying controls/topics; they do not establish universal settings or claim
that these steps reproduce an artist's process. Existing artist examples remain
optional. No online material has execution authority.

The reference brief records a selected file passage, focus dimensions and the
user's own notes. A second selected passage can be measured for comparison.
Diagnostic band differences are normalized for integrated loudness and common
frequency bounds. No automatic EQ matching, inferred stems/gear or perceptual
similarity score is produced. Arrangement and effects require human interpretation.
The reference audio is never copied into the output or uploaded to GitHub.

Sample editing supports at least 10 ms one-shots, explicit trims/reversal/fades,
gain and optional peak normalization. Files are new 24-bit WAVs; their source is
preserved. Processing uses float64 and checks finite/non-silent/clipping state
before writing. Native warp, pitch and slicing-to-MIDI remain documented methods.

Master versions use dynamic, balanced and dense starting profiles. Each uses this
tool's existing linked limiter with different target, release, lookahead and gain
reduction budget. They are not genre standards or a FabFilter emulation. Each
version starts with the same source and retains its own decisions/metrics. Shared
comparison copies attenuate to the quietest version's LUFS; no version is chosen
as the creative winner. Parent links require a source hash found among the parent's
recorded outputs, including its matched copies.

Verification criteria are in acceptance/CREATIVE-REQUIREMENTS.md. The extension
adds 13 cases to the previous 58. A fresh independent reviewer reproduced a
float32 overflow on an extreme but finite source; float64 processing plus explicit
post-DSP checks and a regression repair address it. Actual pinned Proof Loop run
reports retain their own candidate hashes and acceptance remains not_accepted.
Same-user protected tests are not independent custody or a perceptual listener.

The real pipeline exercise used this project's existing test bounces, not a user
reference or commercial track. It produced dynamic/balanced/dense masters at
approximately −15.63 / −12.95 / −9.84 LUFS, with estimated true peaks near −1 dBTP.
Their comparison copies matched near −15.63 LUFS. A separate reversed/faded
400 ms sample and an 8-second reference brief were written without playback.
Those historical local smoke results are not bundled in the public export. Current public demo measurements are in [DEMO-RESULTS.json](DEMO-RESULTS.json); audio/evidence stay ignored.
