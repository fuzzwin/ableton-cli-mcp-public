import json
import shlex
import sys
from pathlib import Path
import click
from . import __version__
from .als import inspect_set
from .bridge import strict_json
from .client import Client
from .install import install_bridge
from .service import ControlError
from .policy import guard_playback
from .utils.repl_skin import ReplSkin


def output(ctx, result):
    if ctx.find_root().obj["json"]:
        click.echo(json.dumps(result, separators=(",", ":"), allow_nan=False))
    else:
        click.echo(json.dumps(result, indent=2, allow_nan=False))


def invoke(ctx, method, params=None, request_id=None):
    output(ctx, ctx.find_root().obj["client"].call(method, params, request_id))


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Compact machine-readable JSON")
@click.option("--config", type=click.Path(path_type=Path), help="Private bridge configuration path")
@click.option("--workspace", type=click.Path(exists=True, file_okay=False, path_type=Path), help="Directory for opt-in silent production tools")
@click.option("--allow-playback", is_flag=True, help="Explicitly allow Live play/clip launch; default is silent")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, as_json, config, workspace, allow_playback):
    """Agent-native Ableton Live commands and interactive REPL."""
    ctx.obj = {"json": as_json, "client": Client(config), "config": config, "workspace": workspace, "allow_playback": allow_playback}
    ctx.call_on_close(ctx.obj["client"].close)
    if ctx.invoked_subcommand is None:
        if not sys.stdin.isatty():
            raise ControlError("Choose a command; use --help or mcp for MCP stdio")
        ctx.invoke(repl)


for command in ("status", "capabilities"):
    def make_read(name):
        @click.command(name)
        @click.pass_context
        def read(ctx):
            invoke(ctx, name)
        return read
    cli.add_command(make_read(command))


@cli.command()
@click.option("--offset", type=int, default=0)
@click.option("--limit", type=int, default=32)
@click.pass_context
def tracks(ctx, offset, limit):
    """List a page of tracks and devices."""
    invoke(ctx, "tracks", {"offset": offset, "limit": limit})


@cli.command()
@click.argument("track", type=int)
@click.argument("device", type=int)
@click.option("--offset", type=int, default=0)
@click.option("--limit", type=int, default=32)
@click.pass_context
def parameters(ctx, track, device, offset, limit):
    """Inspect device parameter bounds and current values."""
    invoke(ctx, "parameters", {"track": track, "device": device, "offset": offset, "limit": limit})


@cli.command()
@click.argument("track", type=int)
@click.argument("slot", type=int)
@click.option("--notes", is_flag=True)
@click.option("--offset", type=int, default=0)
@click.option("--limit", type=int, default=32)
@click.pass_context
def clip(ctx, track, slot, notes, offset, limit):
    """Inspect a Session clip and optionally its MIDI notes."""
    invoke(ctx, "clip", {"track": track, "slot": slot, "include_notes": notes, "offset": offset, "limit": limit})


@cli.group("set")
def set_group():
    """Read native Ableton project files."""


@set_group.command("inspect")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def inspect_command(ctx, path):
    output(ctx, inspect_set(path))


@cli.command()
@click.argument("operations", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session", required=True, help="Current session_id returned by status")
@click.option("--request-id", help="Optional unique mutation identity; never reuse for different edits")
@click.pass_context
def apply(ctx, operations, session, request_id):
    """Apply a JSON array of 1..32 operations. Inspect status first."""
    if operations.stat().st_size > 1024 * 1024:
        raise ControlError("Operation file exceeds 1 MiB")
    values = strict_json(operations.read_bytes())
    if not isinstance(values, list) or any(not isinstance(o, dict) for o in values):
        raise ValueError("Operations must be a JSON array of objects")
    guard_playback(values, ctx.obj["allow_playback"])
    result = ctx.obj["client"].call("apply", {"session_id": session, "operations": values}, request_id)
    output(ctx, result)
    if not result["ok"]:
        ctx.exit(2)


@cli.group()
def bridge():
    """Install the local Ableton Remote Script."""


@bridge.command("install")
@click.option("--user-library", type=click.Path(path_type=Path))
@click.option("--port", type=int, default=9877)
@click.option("--allow-writes", is_flag=True, help="Enable bounded Live edits; default is read-only")
@click.option("--replace", is_flag=True, help="Back up an existing bridge before replacing it")
@click.pass_context
def install(ctx, user_library, port, allow_writes, replace):
    output(ctx, install_bridge(user_library, port, allow_writes, replace))


@cli.command()
@click.option("--allow-writes", is_flag=True)
@click.pass_context
def mcp(ctx, allow_writes):
    """Run the official SDK MCP stdio server."""
    from .mcp_server import create_server
    create_server(ctx.obj["client"], allow_writes, ctx.obj["workspace"], ctx.obj["allow_playback"]).run(transport="stdio")


@cli.group()
def production():
    """Silent file rendering, plugin context and retained evidence; requires --workspace."""


def production_api(ctx):
    from .production.api import Production
    root = ctx.find_root().obj.get("workspace")
    if root is None:
        raise ValueError("Supply --workspace before the production command")
    return Production(root)


@production.command("analyze")
@click.argument("path")
@click.option("--reference")
@click.pass_context
def production_analyze(ctx, path, reference):
    output(ctx, production_api(ctx).analyze(path, reference))


@production.command("mix")
@click.argument("plan_path")
@click.pass_context
def production_mix(ctx, plan_path):
    output(ctx, production_api(ctx).mix(plan_path))


@production.command("master")
@click.argument("path")
@click.option("--target-lufs", type=float, default=-12.0)
@click.option("--ceiling-dbtp", type=float, default=-1.0)
@click.pass_context
def production_master(ctx, path, target_lufs, ceiling_dbtp):
    output(ctx, production_api(ctx).master(path, target_lufs, ceiling_dbtp))


@production.command("plugins")
@click.option("--query", default="")
@click.option("--refresh", is_flag=True)
@click.option("--offset", type=int, default=0)
@click.option("--limit", type=int, default=32)
@click.pass_context
def production_plugins(ctx, query, refresh, offset, limit):
    output(ctx, production_api(ctx).inventory(query, refresh, offset, limit))


@production.command("probe")
@click.argument("plugin_id")
@click.pass_context
def production_probe(ctx, plugin_id):
    output(ctx, production_api(ctx).probe(plugin_id))


@production.command("knowledge")
@click.argument("query")
@click.option("--artist-examples", is_flag=True)
@click.pass_context
def production_knowledge(ctx, query, artist_examples):
    output(ctx, production_api(ctx).knowledge(query, include_artist_examples=artist_examples))


@production.command("recall")
@click.option("--query", default="")
@click.pass_context
def production_recall(ctx, query):
    output(ctx, production_api(ctx).recall(query))


@production.command("feedback")
@click.argument("event_id")
@click.argument("verdict", type=click.Choice(["prefer", "reject", "needs_work"]))
@click.argument("note")
@click.pass_context
def production_feedback(ctx, event_id, verdict, note):
    output(ctx, production_api(ctx).feedback(event_id, verdict, note))


@production.command("methods")
@click.argument("query", default="")
@click.pass_context
def production_methods(ctx, query):
    output(ctx, production_api(ctx).methods(query))


@production.command("prepare")
@click.argument("request_path")
@click.pass_context
def production_prepare(ctx, request_path):
    """Prepare a task request JSON; pure routing after reading the explicit input file."""
    from .preparation import prepare
    api = production_api(ctx)
    output(ctx, prepare(api.workspace.read_json(request_path)))


@production.command("progress")
@click.option("--job-id")
@click.option("--limit",type=int,default=8)
@click.pass_context
def production_progress(ctx,job_id,limit):
    """Read recent observed stages or one job; never creates state."""
    output(ctx,production_api(ctx).progress(job_id,limit))


for workflow_name in ("reference", "sample-edit", "master-versions"):
    def make_workflow(name):
        @click.command(name)
        @click.argument("plan_path")
        @click.pass_context
        def run_workflow(ctx, plan_path):
            output(ctx, getattr(production_api(ctx), name.replace("-", "_"))(plan_path))
        return run_workflow
    production.add_command(make_workflow(workflow_name))


@cli.command()
@click.pass_context
def repl(ctx):
    """Interactive CLI-Anything shell. Use exit to leave."""
    skin = ReplSkin("ableton", version=__version__)
    skin.print_banner()
    session = skin.create_prompt_session()
    try:
        while True:
            try:
                line = skin.get_input(session)
                if line is None or line.strip() in ("exit", "quit"):
                    break
                if not line.strip():
                    continue
                args = shlex.split(line)
                if args[0] in ("repl", "mcp"):
                    skin.error("Use one-shot commands in this shell")
                    continue
                config = ["--config", str(ctx.obj["config"])] if ctx.obj["config"] else []
                work = ["--workspace", str(ctx.obj["workspace"])] if ctx.obj["workspace"] else []
                playback = ["--allow-playback"] if ctx.obj["allow_playback"] else []
                cli.main(args=config + work + playback + args, standalone_mode=False)
            except (ControlError, click.ClickException, ValueError) as exc:
                skin.error(str(exc))
            except (EOFError, KeyboardInterrupt):
                break
    finally:
        skin.print_goodbye()


def main():
    try:
        code = cli(standalone_mode=False)
        if isinstance(code, int) and code:
            raise SystemExit(code)
    except (ControlError, OSError, ValueError, RuntimeError, click.ClickException, click.Abort) as exc:
        if "--json" in sys.argv:
            click.echo(json.dumps({"ok": False, "error": str(exc)}))
        else:
            click.echo("Error: " + str(exc), err=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
