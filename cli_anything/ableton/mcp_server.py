"""Official MCP SDK stdio transport. No HTTP listener is exposed."""
import argparse
import json
import anyio
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictBool, StrictStr
from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations, CallToolResult, TextContent
from .als import inspect_set
from .client import Client
from .policy import guard_playback
from .preparation import CORE_INSTRUCTIONS, Task, prepare, workflow_prompt


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Note(StrictModel):
    pitch: int = Field(ge=0, le=127)
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    velocity: int = Field(ge=1, le=127)
    mute: bool = False


class Tempo(StrictModel):
    op: Literal["tempo"]
    bpm: float = Field(ge=20, le=999)


class Transport(StrictModel):
    op: Literal["transport"]
    action: Literal["play", "stop"]


class TrackCreate(StrictModel):
    op: Literal["track_create"]
    kind: Literal["midi", "audio"]
    name: str = Field(min_length=1, max_length=128)


class TrackSet(StrictModel):
    op: Literal["track_set"]
    track: int = Field(ge=0)
    name: str | None = None
    mute: bool | None = None
    solo: bool | None = None
    volume: float | None = Field(default=None, ge=0, le=1)
    pan: float | None = Field(default=None, ge=-1, le=1)


class ParameterSet(StrictModel):
    op: Literal["parameter_set"]
    track: int = Field(ge=0)
    device: int = Field(ge=0)
    parameter: int = Field(ge=0)
    value: float


class ClipCreate(StrictModel):
    op: Literal["clip_create"]
    track: int = Field(ge=0)
    slot: int = Field(ge=0)
    length: float = Field(ge=1 / 960, le=65536)
    name: str | None = None
    notes: list[Note] = Field(default_factory=list, max_length=4096)


class ClipFire(StrictModel):
    op: Literal["clip_fire"]
    track: int = Field(ge=0)
    slot: int = Field(ge=0)


class ClipStop(StrictModel):
    op: Literal["clip_stop"]
    track: int = Field(ge=0)
    slot: int = Field(ge=0)


Operation = Annotated[Union[Tempo, Transport, TrackCreate, TrackSet, ParameterSet,
                           ClipCreate, ClipFire, ClipStop], Field(discriminator="op")]


class StrictMCP(FastMCP):
    """Reject unknown arguments before FastMCP's permissive argument parsing."""
    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema["additionalProperties"] = False
        return tools

    async def call_tool(self, name, arguments):
        if not hasattr(self, "_argument_validators"):
            self._argument_validators = {tool.name: Draft202012Validator(tool.inputSchema)
                                         for tool in await self.list_tools()}
        validator = self._argument_validators.get(name)
        if validator is None:
            raise ToolError("Unknown tool: " + name)
        error = next(validator.iter_errors(arguments), None)
        if error is not None:
            raise ToolError("Invalid tool arguments: " + error.message)
        return await super().call_tool(name, arguments)


def create_server(client=None, allow_writes=False, workspace=None, allow_playback=False):
    backend = client or Client()
    instructions = CORE_INSTRUCTIONS + ("" if workspace is not None else "\nThis connection has no production workspace: only native inspection and explicitly enabled native edits are exposed; ableton_prepare and file workflows are unavailable.")
    server = StrictMCP("Ableton CLI-Anything", instructions=instructions)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.prompt(name="ableton_workflow", description="Prepare a concise musical task with selective context and honest capabilities. Selected explicitly by the user/client; not an automatic hook.")
    def reusable_workflow(task: str, request: str, source: str | None = None, reference: str | None = None,
                          style: str = "", constraints: str = "", plugin_query: str | None = None) -> str:
        return workflow_prompt({"task":task, "request":request, "source":source, "reference":reference,
                                "style":style, "constraints":constraints, "plugin_query":plugin_query},
                               workspace_enabled=workspace is not None, allow_writes=allow_writes, allow_playback=allow_playback)

    @server.tool(annotations=read)
    def ableton_status() -> dict:
        """Compact live session ID, tempo, transport and counts. Call before edits."""
        return backend.call("status")

    @server.tool(annotations=read)
    def ableton_capabilities() -> dict:
        """List available edit operations, argument names and hard limits."""
        return backend.call("capabilities")

    @server.tool(annotations=read)
    def ableton_tracks(offset: StrictInt = 0, limit: StrictInt = 32) -> dict:
        """Page tracks and top-level device names. Limit 1..128."""
        return backend.call("tracks", {"offset": offset, "limit": limit})

    @server.tool(annotations=read)
    def ableton_parameters(track: StrictInt, device: StrictInt, offset: StrictInt = 0, limit: StrictInt = 32) -> dict:
        """Page a device's parameters with native value bounds. Limit 1..512."""
        return backend.call("parameters", {"track": track, "device": device, "offset": offset, "limit": limit})

    @server.tool(annotations=read)
    def ableton_clip(track: StrictInt, slot: StrictInt, include_notes: StrictBool = False, offset: StrictInt = 0, limit: StrictInt = 32) -> dict:
        """Inspect one Session clip, optionally a page of MIDI notes. Limit 1..512."""
        return backend.call("clip", {"track": track, "slot": slot, "include_notes": include_notes,
                                     "offset": offset, "limit": limit})

    @server.tool(annotations=read)
    def ableton_inspect_set(path: StrictStr) -> dict:
        """Read a local .als file without changing or opening it. Works while Live is disconnected."""
        return inspect_set(path)

    if allow_writes:
        @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                                idempotentHint=False, openWorldHint=False))
        def ableton_apply(session_id: StrictStr, operations: list[Operation], request_id: StrictStr | None = None) -> CallToolResult:
            """Apply 1..32 prevalidated edits in one undo group. Bridge must enable writes.

            clip_create requires an empty MIDI Session slot. Notes use pitch 0..127,
            start/duration in beats, velocity 1..127. All targets must already exist.
            A failed native call may have applied part of the batch: inspect before acting.
            """
            values = [o.model_dump(exclude_none=True) for o in operations]
            guard_playback(values, allow_playback)
            result = backend.call("apply", {"session_id": session_id,
                                            "operations": values}, request_id)
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))],
                                  structuredContent=result, isError=not result["ok"])
    if workspace is not None:
        from .production.api import Production
        production = Production(workspace)
        local_write = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
        production_limiter = anyio.CapacityLimiter(2)

        async def run_production(ctx, function, *args):
            from .production.progress import observe
            def notify(job):
                current=next((s["label"] for s in job["stages"] if s["id"]==job["current_stage"]),"Starting")
                message=f"{job['operation']}: {current} · {job['completed_stages']}/{job['total_stages']} stages · {job['state']} · job {job['job_id']}"
                if job.get("items"):
                    message+=f" · {job['items']['completed']}/{job['items']['total']} items"
                # Sequence counts observed events; it is not time percentage.
                anyio.from_thread.run(ctx.report_progress,float(job["sequence"]),None,message)
            def work():
                with observe(notify):
                    return function(*args)
            try:
                await ctx.report_progress(0,None,"Queued for a production worker · 0 stages observed")
            except Exception:
                pass
            return await anyio.to_thread.run_sync(work,limiter=production_limiter)

        @server.tool(annotations=read)
        def ableton_progress(job_id: StrictStr | None = None, limit: StrictInt = 8) -> dict:
            """Read recent production job stages, item counts and outcomes, or one progress_job_id. No state creation, audio read or playback. Stale heartbeat means unconfirmed, not success."""
            return production.progress(job_id,limit)

        @server.tool(annotations=read)
        def ableton_prepare(task: Task, request: StrictStr, source: StrictStr | None = None, reference: StrictStr | None = None,
                            style: StrictStr = "", constraints: StrictStr = "", plugin_query: StrictStr | None = None) -> dict:
            """Start a NEW multi-step music task with a compact route and selective context. Pure planning; no I/O. Skip for simple reads; do not repeat after every call.

            source: relative audio for analyze/master, or JSON plan for mix/reference/sample_edit/master_versions.
            reference: optional relative reference audio; style/constraints describe the user's intent.
            plugin_query: only an explicitly relevant plugin. Missing JSON plans are agent-authored, not a request for the user to write them.
            """
            return prepare({"task":task, "request":request, "source":source, "reference":reference,
                            "style":style, "constraints":constraints, "plugin_query":plugin_query},
                           workspace_enabled=True, allow_writes=allow_writes, allow_playback=allow_playback)

        @server.tool(annotations=local_write)
        async def ableton_audio_analyze(ctx: Context, path: StrictStr, reference: StrictStr | None = None) -> dict:
            """Analyze bounced WAV/AIFF/FLAC inside the workspace and log evidence. Optional level-matched reference metrics. No playback or perceptual audition."""
            return await run_production(ctx, production.analyze, path, reference)

        @server.tool(annotations=local_write)
        async def ableton_mix(ctx: Context, plan_path: StrictStr) -> dict:
            """Render an explicit JSON stem plan to NEW premaster/master files and record checks. Relative workspace paths; never changes sources or Live."""
            return await run_production(ctx, production.mix, plan_path)

        @server.tool(annotations=local_write)
        async def ableton_master(ctx: Context, path: StrictStr, target_lufs: float = -12.0, ceiling_dbtp: float = -1.0) -> dict:
            """Master a bounced file to a NEW directory using at most two measured candidates. Targets are starting points, not genre mandates. No playback."""
            return await run_production(ctx, production.master, path, target_lufs, ceiling_dbtp)

        @server.tool(annotations=local_write)
        async def ableton_plugin_inventory(ctx: Context, query: StrictStr = "", refresh: StrictBool = False, offset: StrictInt = 0, limit: StrictInt = 32) -> dict:
            """Page local plugin metadata and recorded probe outcomes. Refresh reads bundle metadata only; installed is not proven usable."""
            return await run_production(ctx, production.inventory, query, refresh, offset, limit)

        @server.tool(annotations=local_write)
        async def ableton_plugin_probe(ctx: Context, plugin_id: StrictStr) -> dict:
            """Explicitly load ONE indexed VST3/AU in a bounded child and render a test file. May trigger vendor licensing UI. No audio output device; native Live remains unverified."""
            return await run_production(ctx, production.probe, plugin_id)

        @server.tool(annotations=read)
        def ableton_knowledge(query: StrictStr, limit: StrictInt = 8, include_artist_examples: StrictBool = False) -> dict:
            """Retrieve versioned guide/source cards by tool, topic or style. Artist examples are optional. Refresh current claims from their primary URLs."""
            return production.knowledge(query, limit, include_artist_examples)

        @server.tool(annotations=local_write)
        def ableton_feedback(event_id: StrictStr, verdict: Literal["prefer", "reject", "needs_work"], note: StrictStr, tags: list[StrictStr] | None = None) -> dict:
            """Record explicit HUMAN feedback about an existing event. Do not fabricate user preference from technical metrics."""
            return production.feedback(event_id, verdict, note, tags)

        @server.tool(annotations=local_write)
        def ableton_recall(query: StrictStr = "", limit: StrictInt = 20) -> dict:
            """Retrieve local measured outcomes and separately labelled feedback for future work. Creates a ledger if absent; does not train a model."""
            return production.recall(query, limit)

        @server.tool(annotations=read)
        def ableton_methods(query: StrictStr = "", limit: StrictInt = 8) -> dict:
            """Source-backed editing, sampling, effects, style, mixing and mastering methods. Explicitly separates executable file operations from native/manual techniques."""
            return production.methods(query, limit)

        @server.tool(annotations=local_write)
        async def ableton_reference(ctx: Context, plan_path: StrictStr) -> dict:
            """Create a local reference brief from user-selected passages, focus and notes. Optional candidate metrics; no audio copying, EQ cloning or perceptual similarity claim."""
            return await run_production(ctx, production.reference, plan_path)

        @server.tool(annotations=local_write)
        async def ableton_sample_edit(ctx: Context, plan_path: StrictStr) -> dict:
            """Explicit JSON trim/reverse/fades/gain plan to a NEW sample WAV. Short one-shots supported. No playback or native warping."""
            return await run_production(ctx, production.sample_edit, plan_path)

        @server.tool(annotations=local_write)
        async def ableton_master_versions(ctx: Context, plan_path: StrictStr) -> dict:
            """Create up to three named dynamic/balanced/dense masters from the same source, with intent, hashes, optional parent lineage and level-matched copies. No subjective winner is chosen."""
            return await run_production(ctx, production.master_versions, plan_path)
    return server


def main():
    parser = argparse.ArgumentParser(description="Ableton MCP via official SDK stdio")
    parser.add_argument("--config")
    parser.add_argument("--allow-writes", action="store_true", help="Expose mutation tool; bridge also needs write enablement")
    parser.add_argument("--workspace", help="Existing directory for opt-in silent production tools")
    parser.add_argument("--allow-playback", action="store_true", help="Explicitly allow Live play/clip launch; default is silent")
    args = parser.parse_args()
    backend = Client(args.config)
    try:
        create_server(backend, args.allow_writes, args.workspace, args.allow_playback).run(transport="stdio")
    finally:
        backend.close()


if __name__ == "__main__":
    main()
