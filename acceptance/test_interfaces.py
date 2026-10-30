import asyncio
import gzip
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_transport import RunningBridge


def _resolve_cli(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError("Installed command required: " + name)
    return path


class Interfaces(unittest.TestCase):
    def setUp(self):
        self.server = RunningBridge()

    def tearDown(self):
        self.server.close()

    def cli(self, *args):
        return subprocess.run([_resolve_cli("cli-anything-ableton"), "--json", "--config", str(self.server.path), *args],
                              capture_output=True, text=True, timeout=10)

    def test_installed_help_and_status(self):
        self.assertEqual(self.cli("--help").returncode, 0)
        result = self.cli("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tempo"], 120)

    def test_cli_errors_are_json(self):
        result = self.cli("parameters", "-1", "0")
        self.assertNotEqual(result.returncode, 0)
        # Click parses negative positional integers; service rejects negative indices.
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_cli_batch_readback(self):
        status = json.loads(self.cli("status").stdout)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edits.json"
            path.write_text(json.dumps([{"op": "tempo", "bpm": 124}, {"op": "track_set", "track": 0, "name": "Keys"}]))
            result = self.cli("apply", str(path), "--session", status["session_id"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["completed"], 2)
            self.assertEqual(json.loads(self.cli("tracks").stdout)["items"][0]["name"], "Keys")

    async def sdk_workflow(self, writes):
        args = ["--config", str(self.server.path)] + (["--allow-writes"] if writes else [])
        parameters = StdioServerParameters(command=_resolve_cli("ableton-mcp"), args=args)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                self.assertEqual("ableton_apply" in names, writes)
                self.assertEqual(len(names), 7 if writes else 6)
                result = await session.call_tool("ableton_status", {})
                self.assertFalse(result.isError)
                status = json.loads(result.content[0].text)
                self.assertEqual(status["tempo"], 120)
                for arguments in [{"offset": False}, {"limit": "1"}, {"extra": "ignored"}]:
                    invalid = await session.call_tool("ableton_tracks", arguments)
                    self.assertTrue(invalid.isError, str(invalid))
                if writes:
                    result = await session.call_tool("ableton_apply", {"session_id": status["session_id"],
                                                       "operations": [{"op": "tempo", "bpm": 126.0}]})
                    self.assertFalse(result.isError, str(result))
                    self.assertEqual(self.server.song.tempo, 126)
                    result = await session.call_tool("ableton_apply", {"session_id": status["session_id"],
                                                       "operations": [{"op": "tempo", "bpm": True}]})
                    self.assertTrue(result.isError)

    def test_official_sdk_read_only_stdio(self):
        asyncio.run(self.sdk_workflow(False))

    def test_official_sdk_write_stdio(self):
        asyncio.run(self.sdk_workflow(True))

    def test_installed_native_file_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.als"
            path.write_bytes(gzip.compress(b'<Ableton Creator="Synthetic"><LiveSet><Tracks/></LiveSet></Ableton>'))
            result = self.cli("set", "inspect", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["read_only"])
