"""Real SDK client checks against the installed silent-production MCP server."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def probe(workspace, master):
    params = StdioServerParameters(command=str(Path(sys.executable).with_name("ableton-mcp")), args=["--workspace", str(workspace.resolve())])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert len(names) == 22 and "ableton_apply" not in names
            results = {}
            for name, args in [("ableton_audio_analyze", {"path":master}),
                               ("ableton_plugin_inventory", {"query":"Diva"}),
                               ("ableton_knowledge", {"query":"techno mastering"}),
                               ("ableton_recall", {"query":"pipeline-smoke", "limit":2})]:
                result = await session.call_tool(name, args)
                assert not result.isError, str(result)
                results[name] = json.loads(result.content[0].text)
            return {"sdk_stdio":True, "tools":names, "live_apply_exposed":False,
                    "analyzed_master":{k:results["ableton_audio_analyze"][k] for k in ["sha256","integrated_lufs","true_peak_4x_dbtp_estimate","clipped_samples","review"]},
                    "diva_inventory_entries":results["ableton_plugin_inventory"]["total"],
                    "guide_cards":len(results["ableton_knowledge"]["cards"]),
                    "recalled_events":len(results["ableton_recall"]["events"]), "speaker_playback":False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--master", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(probe(args.workspace, args.master))
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
