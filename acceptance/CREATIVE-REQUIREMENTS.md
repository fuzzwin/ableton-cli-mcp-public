# Creative workflows and references — bounded extension

1. Source-backed methods cover editing, sampling, effects, mixing decisions,
   style experiments, versions and mastering. Each method names what can execute
   here, what needs native Live/manual work, how to compare, and its limits.
   An artist is never required. Source links and version applicability remain.
2. A user reference brief accepts a workspace-relative audio file, explicit
   musical section, label, focus dimensions and user notes. Store source hash,
   section bounds and measured features locally. An optional candidate section
   produces diagnostic, loudness-normalized differences. Do not copy reference
   audio to output, infer stems/gear/artist technique, auto-match EQ or claim
   perceptual similarity. Invalid sections fail before output.
3. Sample editing trims, optionally reverses, applies fades/gain and optional
   explicit peak normalization to a NEW WAV. Support short one-shots of at least
   10 ms. Preserve the source and reject clipping, path escapes, zero-length or
   invalid fades. Report that warp/pitch/slicing-to-MIDI are native/manual methods.
4. Master-version experiments create at most three named variants from the SAME
   immutable source, with intent, source hash and optional known parent event.
   Dynamic/balanced/dense profiles explicitly vary loudness and timing settings;
   these are authored starting points, not genre mandates or vendor algorithms.
   Write separate masters and attenuated copies matched to a shared LUFS level.
   Record ceiling, target/limiting budget outcomes and creative review pending.
   Do not automatically pick a subjective winner. Never modify or play sources.
5. Expose the above through strict CLI/MCP workspace interfaces. Keep all existing
   bridge and production checks. Version manifests, references and audio remain
   local; publish only source, tests, guide index and sanitized evidence.

Validation remains file/signal based. No new native Live editing, export,
perceptual listener, automatic copying of an artist or model training is claimed.
