import gzip
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from cli_anything.ableton.service import Service, ControlError, validate_operation
from cli_anything.ableton.als import inspect_set


class Parameter:
    name = "Volume"
    min = 0.0
    max = 1.0
    value = 0.5
    is_enabled = True
    is_quantized = False


def song_fixture():
    parameter = Parameter()
    track = NS(name="Piano", has_midi_input=True, has_audio_input=False,
               mute=False, solo=False, arm=False, can_be_armed=True,
               devices=[NS(name="Instrument", class_name="Instrument", parameters=[parameter])],
               mixer_device=NS(volume=parameter, panning=Parameter()),
               clip_slots=[NS(has_clip=False, clip=None)])
    song = NS(name="Synthetic", tempo=120.0, is_playing=False,
              signature_numerator=4, signature_denominator=4, tracks=[track],
              return_tracks=[], scenes=[NS(name="Scene 1")])
    song.start_playing = lambda: setattr(song, "is_playing", True)
    song.stop_playing = lambda: setattr(song, "is_playing", False)
    song.begin_undo_step = lambda: None
    song.end_undo_step = lambda: None
    return song


class Contract(unittest.TestCase):
    def setUp(self):
        self.song = song_fixture()
        self.service = Service(lambda: self.song, allow_writes=True)
        self.session = self.service.execute("status", {})["session_id"]

    def apply(self, operations, session=None, request_id="test"):
        return self.service.execute("apply", {"session_id": session or self.session,
                                             "operations": operations}, request_id)

    def test_read_status_is_compact(self):
        status = self.service.execute("status", {})
        self.assertEqual(status["tempo"], 120.0)
        self.assertEqual(status["track_count"], 1)
        self.assertNotIn("tracks", status)

    def test_stale_session_rejected(self):
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 128}], "stale")
        self.assertEqual(self.song.tempo, 120.0)

    def test_song_switch_invalidates_session(self):
        self.song = song_fixture()
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 128}])

    def test_equal_native_wrappers_preserve_session(self):
        class NativeProxy:
            def __init__(self, target):
                self.target = target

            def __getattr__(self, name):
                return getattr(self.target, name)

            def __eq__(self, other):
                return isinstance(other, NativeProxy) and self.target is other.target

            def __ne__(self, other):
                return not self == other

        service = Service(lambda: NativeProxy(self.song))
        initial = service.execute("status", {})["session_id"]
        for unused in range(3):
            self.assertEqual(service.execute("status", {})["session_id"], initial)
        self.song = song_fixture()
        self.assertNotEqual(service.execute("status", {})["session_id"], initial)

    def test_read_only_blocks_edits(self):
        self.service.allow_writes = False
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 128}])

    def test_full_batch_preflight(self):
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 128}, {"op": "track_set", "track": 4, "name": "x"}])
        self.assertEqual(self.song.tempo, 120.0)

    def test_batch_limit(self):
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 128}] * 33)

    def test_idempotency_and_collision(self):
        operations = [{"op": "tempo", "bpm": 128}]
        result = self.apply(operations)
        self.song.tempo = 110
        self.assertEqual(self.apply(operations), result)
        self.assertEqual(self.song.tempo, 110)
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 129}])

    def test_number_and_unknown_field_rejection(self):
        for value in [True, float("nan"), float("inf"), -1, 1001, "120"]:
            with self.subTest(value=value), self.assertRaises(ControlError):
                validate_operation({"op": "tempo", "bpm": value})
        with self.assertRaises(ControlError):
            validate_operation({"op": "tempo", "bpm": 120, "shell": "ignored"})

    def test_note_validation(self):
        valid = {"pitch": 60, "start": 0.0, "duration": 0.5, "velocity": 100, "mute": False}
        validate_operation({"op": "clip_create", "track": 0, "slot": 0, "length": 4, "notes": [valid]})
        for change in [{"pitch": -1}, {"pitch": True}, {"velocity": 128}, {"duration": 0},
                       {"start": -1}, {"mute": 1}, {"duration": float("nan")}, {"extra": 1}]:
            with self.subTest(change=change), self.assertRaises(ControlError):
                validate_operation({"op": "clip_create", "track": 0, "slot": 0, "length": 4,
                                    "notes": [{**valid, **change}]})

    def test_notes_outside_clip_rejected(self):
        with self.assertRaises(ControlError):
            validate_operation({"op": "clip_create", "track": 0, "slot": 0, "length": 4,
                                "notes": [{"pitch": 60, "start": 3.5, "duration": 1, "velocity": 100}]})

    def test_negative_index_and_pagination(self):
        with self.assertRaises(ControlError):
            self.service.execute("parameters", {"track": -1, "device": 0})
        page = self.service.execute("tracks", {"offset": 0, "limit": 1})
        self.assertEqual(page["total"], 1)
        self.assertEqual(len(page["items"]), 1)

    def test_empty_clip_rejects_invalid_flag(self):
        with self.assertRaises(ControlError):
            self.service.execute("clip", {"track": 0, "slot": 0, "include_notes": "bad"})

    def test_total_note_budget(self):
        note = {"pitch": 60, "start": 0, "duration": 1, "velocity": 100}
        op = {"op": "clip_create", "track": 0, "slot": 0, "length": 4, "notes": [note] * 2049}
        with self.assertRaisesRegex(ControlError, "in total"):
            self.apply([op, op])

    def test_parameter_bounds_checked_before_mutation(self):
        with self.assertRaises(ControlError):
            self.apply([{"op": "tempo", "bpm": 128},
                        {"op": "parameter_set", "track": 0, "device": 0, "parameter": 0, "value": 2}])
        self.assertEqual(self.song.tempo, 120)

    def test_unknown_and_arbitrary_execution_rejected(self):
        for method in ["eval", "save", "delete_track", "record", "render"]:
            with self.subTest(method=method), self.assertRaises(ControlError):
                self.service.execute(method, {})

    def test_partial_failure_reports_completed_prefix(self):
        def fail():
            raise RuntimeError("Synthetic engine error")
        self.song.start_playing = fail
        result = self.apply([{"op": "tempo", "bpm": 128}, {"op": "transport", "action": "play"}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(self.song.tempo, 128)
        self.assertFalse(result["rolled_back"])


class NativeSet(unittest.TestCase):
    def test_compressed_set_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.als"
            content = gzip.compress(b'<Ableton MajorVersion="5" Creator="Ableton Live 11"><LiveSet><Tracks><MidiTrack Id="0"><Name><EffectiveName Value="Piano"/></Name></MidiTrack></Tracks><MasterTrack><DeviceChain><Mixer><Tempo><Manual Value="123"/></Tempo></Mixer></DeviceChain></MasterTrack></LiveSet></Ableton>')
            path.write_bytes(content)
            info = inspect_set(str(path))
            self.assertEqual(info["tracks"][0]["name"], "Piano")
            self.assertEqual(info["tempo"], 123)
            self.assertEqual(path.read_bytes(), content)

    def test_xml_entities_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.als"
            path.write_bytes(gzip.compress(b'<!DOCTYPE x [<!ENTITY a "x">]><Ableton>&a;</Ableton>'))
            with self.assertRaises(ControlError):
                inspect_set(str(path))

    def test_decompression_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.als"
            path.write_bytes(gzip.compress(b" " * 1000))
            with self.assertRaises(ControlError):
                inspect_set(str(path), max_bytes=100)
