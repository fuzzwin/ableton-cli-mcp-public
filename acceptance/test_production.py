import asyncio
import hashlib
import json
import os
import plistlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import soundfile as sf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from cli_anything.ableton.production.workspace import Workspace, digest
from cli_anything.ableton.production import audio, knowledge, plugins
from cli_anything.ableton.production.render import render_mix, render_master
from cli_anything.ableton.production.ledger import Ledger
from cli_anything.ableton.mcp_server import create_server
from cli_anything.ableton.policy import guard_playback
from cli_anything.ableton.service import ControlError


class Production(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = Workspace(self.root)
        self.sr = 16000
        t = np.arange(self.sr * 2) / self.sr
        self.signal = (.1 * np.sin(2 * np.pi * 90 * t)).astype(np.float32)
        self.write("tone.wav", np.column_stack([self.signal, self.signal]))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data, sr=None):
        sf.write(self.root / name, data, sr or self.sr, subtype="FLOAT")

    def test_workspace_traversal_and_symlink_escape(self):
        with self.assertRaises(ValueError):
            self.workspace.path("../outside", exists=False)
        with self.assertRaises(ValueError):
            self.workspace.path(str(self.root / "tone.wav"))
        (self.root / "escape").symlink_to("/private/tmp", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.workspace.path("escape/out.wav", exists=False)
        (self.root / ".ableton-harness").symlink_to("/private/tmp", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.workspace.state_dir()

    def test_silence_invalid_and_oversized_channels(self):
        for name, data in [("silent.wav", np.zeros(self.sr)), ("nan.wav", np.full(self.sr, np.nan)),
                           ("surround.wav", np.zeros((self.sr, 6)))]:
            self.write(name, data)
            with self.assertRaises(ValueError):
                audio.analyze(self.root / name)

    def test_analysis_hash_peak_loudness_and_no_audition(self):
        report = audio.analyze(self.root / "tone.wav")
        self.assertEqual(report["sha256"], digest(self.root / "tone.wav"))
        self.assertEqual(report["clipped_samples"], 0)
        self.assertAlmostEqual(report["sample_peak_dbfs"], -20, delta=.01)
        self.assertLess(report["integrated_lufs"], -20)
        self.assertFalse(report["review"]["speaker_playback"])
        self.assertFalse(report["review"]["perceptual_listening"])

    def test_chunked_true_peak_matches_full_interpolation(self):
        from scipy.signal import resample_poly
        sr = 44100
        t = np.arange(sr * 5) / sr
        for frequency in (20, 1000):
            x = np.sin(2 * np.pi * frequency * t).astype(np.float32)
            x[:sr // 10] *= np.linspace(0, 1, sr // 10)
            x[-sr // 10:] *= np.linspace(1, 0, sr // 10)
            x = np.column_stack([x, x])
            expected = float(np.max(np.abs(resample_poly(x, 4, 1, axis=0))))
            self.assertAlmostEqual(audio.true_peak(x), expected, delta=1e-6)

    def test_visual_source_drift_marks_results_historical(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("proof_visual", Path(__file__).resolve().parents[1] / "scripts/proof_visual.py")
        visual = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(visual)
        visual.ROOT = self.root
        runtime = self.root / ".runtime"
        runtime.mkdir()
        source = self.root / "tone.wav"
        (runtime / "visual.json").write_text(json.dumps({"phase":"checks complete", "verification":{"state":"pass"},
            "input_manifest":{"tone.wav":{"sha256":digest(source),"mode":source.stat().st_mode & 0o777}}}))
        self.assertEqual(visual.state()["live_freshness"]["state"], "current")
        source.write_bytes(b"changed")
        result = visual.state()
        self.assertEqual(result["live_freshness"]["state"], "stale")
        self.assertIsNone(result["verification"])

    def test_corrupt_audio_cli_error_is_json(self):
        (self.root / "broken.wav").write_text("not audio")
        result = subprocess.run([shutil.which("cli-anything-ableton"), "--json", "--workspace", str(self.root),
                                 "production", "analyze", "broken.wav"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertNotIn("Traceback", result.stderr)

    def test_antiphase_mono_loss_is_detected(self):
        self.write("anti.wav", np.column_stack([self.signal, -self.signal]))
        report = audio.analyze(self.root / "anti.wav")
        self.assertLess(report["stereo_correlation"], -.99)
        self.assertLess(report["mono_fold_loss_db"], -100)

    def test_clipping_is_detected(self):
        self.write("hot.wav", np.tile([[1.2, -1.2]], (self.sr, 1)))
        report = audio.analyze(self.root / "hot.wav")
        self.assertEqual(report["clipped_samples"], self.sr * 2)

    def test_level_matched_comparison(self):
        self.write("quiet.wav", np.column_stack([self.signal, self.signal]) * .5)
        report = audio.compare(self.root / "quiet.wav", self.root / "tone.wav")
        self.assertAlmostEqual(report["level_match_db"], 6.0206, delta=.05)
        self.assertAlmostEqual(report["crest_delta_db"], 0, delta=.05)
        self.assertLess(max(abs(b["delta"]) for b in report["spectral_balance_delta_db"]), .05)

    def test_master_preserves_input_and_checks_ceiling(self):
        before = digest(self.root / "tone.wav")
        report = render_master(self.workspace, "tone.wav", target=-14, ceiling=-1)
        self.assertEqual(digest(self.root / "tone.wav"), before)
        self.assertLessEqual(report["master"]["true_peak_4x_dbtp_estimate"], -.98)
        self.assertEqual(report["master"]["clipped_samples"], 0)
        self.assertLessEqual(len(report["mastering"]["candidates"]), 2)
        self.assertTrue(self.workspace.path(report["output_directory"] + "/master.wav").exists())
        self.assertEqual(report["mastering"]["creative_acceptance"], "pending")

    def test_mix_validation_and_new_output(self):
        self.write("sub.wav", np.column_stack([self.signal, self.signal]) * .5)
        plan = {"stems": [{"path": "tone.wav", "role": "kick"}, {"path": "sub.wav", "role": "sub", "duck_db": 4.0}],
                "duck_source": "tone.wav", "auto_balance": True, "tags": ["test"]}
        before = digest(self.root / "tone.wav")
        a, b = render_mix(self.workspace, plan), render_mix(self.workspace, plan)
        self.assertTrue(a["technical_pass"])
        self.assertNotEqual(a["output_directory"], b["output_directory"])
        self.assertEqual(before, digest(self.root / "tone.wav"))
        self.assertTrue(all(abs(m["automatic_gain_db"]) <= 3 for m in a["moves"]))
        self.assertLessEqual(a["headroom_gain_db"], 0)

    def test_invalid_plan_does_not_render(self):
        for plan in [
            {"stems": [{"path":"tone.wav", "role":"kick", "typo":1}]},
            {"stems": [{"path":"tone.wav", "role":"sub", "duck_db":4}]},
            {"stems": [{"path":"tone.wav", "role":"kick"}], "max_attempts":3},
            {"stems": [{"path":"tone.wav", "role":"kick"}], "auto_balance":True},
            {"stems": [{"path":"tone.wav", "role":"kick", "gain_db":float("nan")}]},
        ]:
            with self.assertRaises(ValueError):
                render_mix(self.workspace, plan)
        self.assertFalse((self.root / "renders").exists())

    def test_mismatched_stems_fail_before_output(self):
        self.write("short.wav", self.signal[:self.sr])
        with self.assertRaises(ValueError):
            render_mix(self.workspace, {"stems": [{"path":"tone.wav","role":"kick"}, {"path":"short.wav","role":"sub"}]})
        self.assertFalse((self.root / "renders").exists())

    def test_metadata_scan_does_not_load_plugins(self):
        root = self.root / "plugins"
        bundle = root / "Test.vst3/Contents"
        (bundle / "MacOS").mkdir(parents=True)
        (bundle / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName":"Test", "CFBundleShortVersionString":"1.2", "CFBundleExecutable":"Test"}))
        (bundle / "MacOS/Test").write_bytes(b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x0100000C) + b"\0" * 32)
        with patch("subprocess.run", side_effect=AssertionError("Metadata scan must not execute")):
            report = plugins.scan([root])
        self.assertEqual(report["loaded_plugins"], 0)
        self.assertEqual(len(report["plugins"]), 1)
        self.assertEqual(report["plugins"][0]["architectures"], ["arm64"])
        self.assertEqual(report["plugins"][0]["offline_status"], "untested")

    def test_knowledge_has_provenance_and_artist_opt_in(self):
        from importlib.resources import files
        from jsonschema import Draft202012Validator, FormatChecker
        package = files("cli_anything.ableton.production").joinpath("data")
        index = json.loads(package.joinpath("knowledge.json").read_text())
        schema = json.loads(package.joinpath("knowledge.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(index)
        self.assertEqual(len({c["id"] for c in index["cards"]}), len(index["cards"]))
        plain = knowledge.search("melodic")
        self.assertTrue(plain["cards"])
        self.assertFalse(any(c["kind"] == "artist_example" for c in plain["cards"]))
        references = knowledge.search("RUFUS", include_artist_examples=True)
        self.assertTrue(any(c["kind"] == "artist_example" for c in references["cards"]))
        for card in knowledge.search("", limit=20, include_artist_examples=True)["cards"]:
            for field in ("url", "authority", "checked", "applies_to", "boundary"):
                self.assertTrue(card[field])

    def test_learning_separates_measurements_from_feedback(self):
        ledger = Ledger(self.workspace)
        event = ledger.append("render", ["techno"], {"technical_pass":True, "creative_acceptance":"pending"})
        ledger.feedback(event, "needs_work", "Lead needs more presence", ["techno"])
        results = ledger.recall("techno")["events"]
        self.assertEqual([r["kind"] for r in results], ["feedback", "render"])
        self.assertEqual(results[0]["payload"]["evidence_type"], "explicit_user_feedback")
        self.assertEqual(results[1]["payload"]["creative_acceptance"], "pending")
        for r in results:
            text = json.dumps(r["payload"], sort_keys=True, allow_nan=False)
            self.assertEqual(r["sha256"], hashlib.sha256(text.encode()).hexdigest())

    def test_unknown_feedback_and_oversized_ledger_rejected(self):
        ledger = Ledger(self.workspace)
        with self.assertRaises(ValueError):
            ledger.feedback("unknown", "prefer", "Great", [])
        with self.assertRaises(ValueError):
            ledger.append("review", [], {"data":"x" * 300000})
        self.assertEqual(ledger.recall("' OR 1=1 --")["events"], [])

    def test_silent_mode_blocks_backend_playback(self):
        for operation in [{"op":"transport", "action":"play"}, {"op":"clip_fire", "track":0, "slot":0}]:
            with self.assertRaises(ControlError):
                guard_playback([operation])
        guard_playback([{"op":"transport", "action":"stop"}])

    def test_mcp_playback_rejected_before_backend(self):
        calls = []
        backend = SimpleNamespace(call=lambda *args: calls.append(args))
        server = create_server(backend, allow_writes=True)
        for operation in [{"op":"transport", "action":"play"}, {"op":"clip_fire", "track":0, "slot":0}]:
            with self.assertRaises(Exception):
                asyncio.run(server.call_tool("ableton_apply", {"session_id":"test", "operations":[operation]}))
        self.assertEqual(calls, [])

    def test_probe_failure_retained_without_playback(self):
        root = self.root / "plugins"
        bundle = root / "Broken.vst3/Contents"
        bundle.mkdir(parents=True)
        (bundle / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName":"Broken"}))
        with patch.object(plugins, "ROOTS", [root]):
            inventory = plugins.inventory(self.workspace, refresh=True)
            result = plugins.probe(self.workspace, inventory["plugins"][0]["id"])
            self.assertEqual(result["status"], "load_error")
            self.assertFalse(result["speaker_playback"])
            saved = plugins.inventory(self.workspace)
            self.assertEqual(saved["plugins"][0]["offline_status"], "load_error")

    def test_changed_plugin_invalidates_probe(self):
        root = self.root / "plugins"
        bundle = root / "Test.vst3/Contents"
        bundle.mkdir(parents=True)
        plist = bundle / "Info.plist"
        plist.write_bytes(plistlib.dumps({"CFBundleName":"Test", "CFBundleVersion":"1"}))
        with patch.object(plugins, "ROOTS", [root]):
            before = plugins.inventory(self.workspace, refresh=True)
            plugins.probe(self.workspace, before["plugins"][0]["id"])
            plist.write_bytes(plistlib.dumps({"CFBundleName":"Test", "CFBundleVersion":"2"}))
            after = plugins.inventory(self.workspace, refresh=True)
        self.assertNotEqual(before["plugins"][0]["metadata_fingerprint"], after["plugins"][0]["metadata_fingerprint"])
        self.assertEqual(after["plugins"][0]["offline_status"], "untested")

    def test_cli_playback_guard_runs_before_connection(self):
        path = self.root / "play.json"
        path.write_text(json.dumps([{"op":"transport","action":"play"}]))
        proc = subprocess.run([shutil.which("cli-anything-ableton"), "--json", "--config", str(self.root / "missing-config.json"),
                               "apply", str(path), "--session", "test"], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Silent mode blocks", json.loads(proc.stdout)["error"])

    def test_no_output_device_dependencies(self):
        source = Path(audio.__file__).parent
        # Code-level invariant plus real file tests. Does not sandbox third-party plugins.
        for path in source.glob("*.py"):
            text = path.read_text()
            for forbidden in ("AudioStream(", "sounddevice", "pyaudio", "start_playing(", "afplay"):
                self.assertNotIn(forbidden, text, str(path))

    def test_cli_requires_explicit_workspace(self):
        cli = shutil.which("cli-anything-ableton")
        proc = subprocess.run([cli, "--json", "production", "knowledge", "techno"], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(json.loads(proc.stdout)["ok"])

    async def sdk(self):
        params = StdioServerParameters(command=shutil.which("ableton-mcp"), args=["--workspace", str(self.root)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = [t.name for t in (await session.list_tools()).tools]
                self.assertIn("ableton_mix", names)
                self.assertNotIn("ableton_apply", names)
                self.assertEqual(len(names), 23)
                report = await session.call_tool("ableton_audio_analyze", {"path":"tone.wav"})
                self.assertFalse(report.isError, str(report))
                result = json.loads(report.content[0].text)
                self.assertEqual(result["clipped_samples"], 0)
                self.assertFalse(result["review"]["speaker_playback"])
                for args in [{"query":"techno","include_artist_examples":"yes"}, {"query":"techno","extra":1}]:
                    bad = await session.call_tool("ableton_knowledge", args)
                    self.assertTrue(bad.isError)
                bad = await session.call_tool("ableton_audio_analyze", {"path":"../escape.wav"})
                self.assertTrue(bad.isError)

    def test_official_mcp_file_only_workflow(self):
        asyncio.run(self.sdk())


if __name__ == "__main__":
    unittest.main()
