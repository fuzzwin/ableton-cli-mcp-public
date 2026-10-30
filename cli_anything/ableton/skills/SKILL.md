---
name: cli-anything-ableton
description: Inspect and control Ableton Live using the local CLI-Anything Remote Script and MCP server. Use for session inspection, tempo, transport, tracks, native device parameters and MIDI Session clips. Optional silent file rendering, mix/master analysis, plugin indexing and evidence retrieval are supported with an explicit workspace. Native arrangement editing, device loading and Ableton export are not supported.
---

Use the installed cli-anything-ableton or ableton-mcp from this project's .venv/bin.
Run cli-anything-ableton --help to inspect current commands. Prefer MCP for repeated
calls because it keeps one process and bridge connection. The server defaults to
six read-only tools. Edits require both bridge and MCP --allow-writes enablement.

First inspect status, then page tracks and parameters. Track/device/slot indices
are zero based. All note and clip times use quarter-note beats; track volume is
linear 0..1. Reinspect after topology changes. Read native .als files with set inspect
without opening or changing them in Live.

CLI examples (global flags come first):

```sh
cli-anything-ableton --json status
cli-anything-ableton --json tracks --limit 16
cli-anything-ableton --json parameters 0 0
cli-anything-ableton --json clip 0 0 --notes --limit 32
cli-anything-ableton --json set inspect /absolute/path/Song.als
cli-anything-ableton --json apply operations.json --session CURRENT_SESSION_ID
```

Use capabilities to inspect operations: tempo, transport play/stop, track_create,
track_set, parameter_set, clip_create, clip_fire and clip_stop. The MCP mutation
tool is ableton_apply with session_id and operations. Each batch is prevalidated,
limited to 32 operations and 4096 notes total, and grouped in one native undo step.
Create a track in one call, inspect its index, then create a clip in another call.
clip_create requires an empty MIDI Session slot. A note is pitch 0..127, start >=0,
duration >0, velocity 1..127, optional boolean mute; it must fit within the clip.

Never automatically retry a mutation after an error, timeout or disconnect.
Inspect Live's actual state first. Partial edits may have occurred even if completed
is zero. Replay protection covers only the last 256 IDs in the current bridge
process; it is not durable exactly-once execution. Do not reuse IDs for other edits.

The bridge is localhost-only with a private token in bridge.json. Never print that
token or copy it into an MCP config. If disconnected, install the Remote Script
using bridge install, then select CLIAnything in Live's MIDI control-surface menu,
with Input/Output None. Ask before restarting Live when unsaved work may be open.
The installer refuses existing files unless --replace is specified and preserves
a backup when replacing. Existing music projects are never automatically saved.

Report synthetic tests, read-only native inspection and actual Live control as
different evidence. Note pagination limits response size but reads the native clip's
full note list. Do not claim realtime safety, rendered audio quality, deployed
service status or independent Proof Loop acceptance from local passing tests.

Production v0.2: supply --workspace /existing/directory to expose fourteen workspace
MCP tools (20 total without Live edits). Use production analyze/mix/master/plugins/
probe/knowledge/recall/feedback in the CLI. Paths are workspace-relative. Always
inspect source provenance, plugin probe state and recent feedback before choosing
tools. The mix plan is explicit JSON; outputs go to a new renders subdirectory.
Never overwrite input bounces or treat a numerical pass as an audition.

Silent mode rejects Live play and clip launch even with --allow-writes. Do not
add --allow-playback unless the human explicitly asks to hear it. Plugin probes
load one explicit indexed VST3/AU in a bounded child and may open vendor licensing
UI; inventory alone never proves usability. Never update or purchase a plugin
automatically. Artist examples in knowledge retrieval require an opt-in and do
not constrain future styles. Refresh changing source facts from primary URLs.

Learning is local evidence/feedback retrieval only. Do not fabricate feedback or
claim model training. Keep audio, local inventory, evidence.sqlite3 and bridge
tokens out of Git. Use actual pinned Proof Loop reports and preserve acceptance
limits; see the repository's USER_GUIDE.md, docs/VERIFICATION.md and AGENTS.md for continuation.

Creative v0.3: production methods retrieves authored workflows with source links.
Use a user-supplied reference plan with a selected section, focus and notes;
reference metrics are not perceptual matching or evidence of the artist's gear.
Sample-edit writes new trim/reverse/fade/gain WAVs; native warp and slicing are
manual. Master-versions writes up to three named dynamic/balanced/dense profiles
from one source plus attenuated level-matched copies. No creative winner is
automatically selected. Parent lineage requires a matching recorded output hash.
Use explicit feedback to store the human's preference, never infer it from LUFS.

Invocation v0.4: for a NEW multi-step production task, call ableton_prepare once
with the current task, musical request and relevant path/context hints. Simple
reads may go directly to their tools. Reuse unchanged evidence, load only the
requested context and keep file workflows independent of Live status. A reusable
ableton_workflow MCP prompt is explicitly selected by the user/client, not an
automatic hook. See docs/INVOCATION-PROMPT.md for the shared instruction and
contract-evaluation limits. The preparation tool itself performs no I/O.

Progress v0.5: tracked production calls return progress_job_id. Share the localhost
stage panel for long work when available; supported clients can display native
MCP notifications. Use ableton_progress for one job or recent activity. Stages and
item counts are observed work, not a time percentage. Needs_attention is a
technical warning; stale/malformed state is unconfirmed. Do not report creative
acceptance from completion. The MCP server has two production workers; status
queries remain responsive. See docs/PRODUCTION-PROGRESS.md.
