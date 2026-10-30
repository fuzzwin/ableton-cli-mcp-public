"""Live Object Model operations. Also copied into Live's Python 3 Remote Script.

No networking or worker threads here: the caller must be Live's main thread.
"""
import hashlib
import json
import math
import uuid
from collections import OrderedDict


class ControlError(ValueError):
    pass


def integer(value, name, low=0, high=2147483647):
    if type(value) is not int or not low <= value <= high:
        raise ControlError("%s must be an integer in %s..%s" % (name, low, high))
    return value


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ControlError("%s must be finite and in %s..%s" % (name, low, high))
    return value


def text(value, name):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        raise ControlError("%s must be 1..128 printable characters" % name)
    return value


FIELDS = {
    "tempo": ({"bpm"}, set()),
    "transport": ({"action"}, set()),
    "track_create": ({"kind", "name"}, set()),
    "track_set": ({"track"}, {"name", "mute", "solo", "volume", "pan"}),
    "parameter_set": ({"track", "device", "parameter", "value"}, set()),
    "clip_create": ({"track", "slot", "length"}, {"name", "notes"}),
    "clip_fire": ({"track", "slot"}, set()),
    "clip_stop": ({"track", "slot"}, set()),
}


def validate_operation(op):
    if not isinstance(op, dict) or op.get("op") not in FIELDS:
        raise ControlError("Unknown operation; use capabilities to list supported operations")
    required, optional = FIELDS[op["op"]]
    if not required <= set(op) or set(op) - required - optional - {"op"}:
        raise ControlError("Missing or unknown fields for " + op["op"])
    for key in ("track", "device", "parameter", "slot"):
        if key in op:
            integer(op[key], key)
    for key in ("name",):
        if key in op:
            text(op[key], key)
    for key in ("mute", "solo"):
        if key in op and type(op[key]) is not bool:
            raise ControlError(key + " must be boolean")
    if op["op"] == "tempo":
        number(op["bpm"], "bpm", 20, 999)
    if op["op"] == "transport" and op["action"] not in ("play", "stop"):
        raise ControlError("action must be play or stop")
    if op["op"] == "track_create" and op["kind"] not in ("midi", "audio"):
        raise ControlError("kind must be midi or audio")
    if op["op"] == "track_set" and not (set(op) & optional):
        raise ControlError("track_set needs at least one changed field")
    if "volume" in op:
        number(op["volume"], "volume (linear)", 0, 1)
    if "pan" in op:
        number(op["pan"], "pan", -1, 1)
    if "value" in op:
        number(op["value"], "value", -1e12, 1e12)
    if op["op"] == "clip_create":
        length = number(op["length"], "length in quarter-note beats", 1.0 / 960, 65536)
        notes = op.get("notes", [])
        if not isinstance(notes, list) or len(notes) > 4096:
            raise ControlError("notes must be an array of at most 4096 notes")
        for note in notes:
            if not isinstance(note, dict) or not {"pitch", "start", "duration", "velocity"} <= set(note) or set(note) - {"pitch", "start", "duration", "velocity", "mute"}:
                raise ControlError("Note fields: pitch, start, duration, velocity, optional mute")
            integer(note["pitch"], "pitch", 0, 127)
            integer(note["velocity"], "velocity", 1, 127)
            number(note["start"], "start", 0, length)
            number(note["duration"], "duration", 1.0 / 960, length)
            if note["start"] + note["duration"] > length + 1e-9:
                raise ControlError("Note ends outside the clip")
            if type(note.get("mute", False)) is not bool:
                raise ControlError("Note mute must be boolean")
    return op


def indexed(items, index, name):
    integer(index, name)
    if index >= len(items):
        raise ControlError("%s index %s out of range (count %s)" % (name, index, len(items)))
    return items[index]


def page(params, maximum=128):
    offset = integer(params.get("offset", 0), "offset")
    limit = integer(params.get("limit", 32), "limit", 1, maximum)
    return offset, limit


class Service:
    def __init__(self, song_getter, allow_writes=False):
        self.song_getter = song_getter
        self.allow_writes = allow_writes
        self._song = None
        self.session_id = None
        # Bounded replay window; requests older than 256 writes must not be retried.
        self.replies = OrderedDict()

    def _current(self):
        song = self.song_getter()
        # Live may return a fresh Python proxy for the same native Song. Proxy
        # equality compares the native object; Python identity does not.
        if self._song is None or song != self._song:
            self._song = song
            self.session_id = str(uuid.uuid4())
        return song

    def execute(self, method, params, request_id=None):
        song = self._current()
        if not isinstance(params, dict):
            raise ControlError("params must be an object")
        allowed = {"status": set(), "capabilities": set(),
                   "tracks": {"offset", "limit"},
                   "parameters": {"track", "device", "offset", "limit"},
                   "clip": {"track", "slot", "offset", "limit", "include_notes"},
                   "apply": {"session_id", "operations"}}
        if method not in allowed or set(params) - allowed[method]:
            raise ControlError("Unknown method or fields")
        if method == "capabilities":
            return {"version": "0.1.0", "writes_enabled": self.allow_writes,
                    "operations": {k: {"required": sorted(v[0]), "optional": sorted(v[1])} for k, v in FIELDS.items()},
                    "max_batch": 32, "max_notes": 4096, "index_base": 0,
                    "time_unit": "quarter-note beats", "retry_mutations": False}
        if method == "status":
            return {"session_id": self.session_id, "tempo": song.tempo,
                    "playing": bool(song.is_playing), "track_count": len(song.tracks),
                    "return_count": len(song.return_tracks), "scene_count": len(song.scenes),
                    "time_signature": [song.signature_numerator, song.signature_denominator],
                    "writes_enabled": self.allow_writes}
        if method == "tracks":
            offset, limit = page(params)
            return {"session_id": self.session_id, "total": len(song.tracks), "offset": offset,
                    "items": [{"index": i, "name": t.name,
                               "kind": "midi" if t.has_midi_input else "audio",
                               "mute": bool(t.mute), "solo": bool(t.solo),
                               "devices": [{"index": j, "name": d.name} for j, d in enumerate(t.devices)],
                               "clip_slots": len(t.clip_slots)}
                              for i, t in enumerate(song.tracks) if offset <= i < offset + limit]}
        if method in ("parameters", "clip"):
            if method == "clip" and type(params.get("include_notes", False)) is not bool:
                raise ControlError("include_notes must be boolean")
            track = indexed(song.tracks, params.get("track"), "track")
            offset, limit = page(params, 512)
            if method == "parameters":
                device = indexed(track.devices, params.get("device"), "device")
                return {"session_id": self.session_id, "total": len(device.parameters), "offset": offset,
                        "items": [{"index": i, "name": p.name, "value": p.value,
                                   "min": p.min, "max": p.max, "enabled": bool(p.is_enabled),
                                   "quantized": bool(p.is_quantized)}
                                  for i, p in enumerate(device.parameters) if offset <= i < offset + limit]}
            slot = indexed(track.clip_slots, params.get("slot"), "slot")
            if not slot.has_clip:
                return {"session_id": self.session_id, "has_clip": False}
            clip = slot.clip
            result = {"session_id": self.session_id, "has_clip": True, "name": clip.name,
                      "length": clip.length, "midi": bool(clip.is_midi_clip),
                      "playing": bool(clip.is_playing)}
            if params.get("include_notes", False) and clip.is_midi_clip:
                notes = clip.get_notes(0.0, 0, clip.length, 128)
                result.update({"total_notes": len(notes), "offset": offset,
                               "notes": [{"pitch": n[0], "start": n[1], "duration": n[2],
                                          "velocity": n[3], "mute": bool(n[4])}
                                         for n in notes[offset:offset + limit]]})
            return result
        return self._apply(song, params, request_id)

    def _prepare(self, song, op):
        kind = op["op"]
        if kind == "tempo":
            return lambda: setattr(song, "tempo", op["bpm"])
        if kind == "transport":
            return song.start_playing if op["action"] == "play" else song.stop_playing
        if kind == "track_create":
            create = song.create_midi_track if op["kind"] == "midi" else song.create_audio_track
            def create_track():
                create(-1)
                song.tracks[-1].name = op["name"]
            return create_track
        track = indexed(song.tracks, op["track"], "track")
        if kind == "track_set":
            def set_track():
                for field in ("name", "mute", "solo"):
                    if field in op:
                        setattr(track, field, op[field])
                if "volume" in op:
                    track.mixer_device.volume.value = op["volume"]
                if "pan" in op:
                    track.mixer_device.panning.value = op["pan"]
            return set_track
        if kind == "parameter_set":
            device = indexed(track.devices, op["device"], "device")
            parameter = indexed(device.parameters, op["parameter"], "parameter")
            if not parameter.is_enabled:
                raise ControlError("Parameter is disabled")
            number(op["value"], "parameter value", parameter.min, parameter.max)
            if parameter.is_quantized and op["value"] != round(op["value"]):
                raise ControlError("Quantized parameters require an integer value")
            return lambda: setattr(parameter, "value", op["value"])
        slot = indexed(track.clip_slots, op["slot"], "slot")
        if kind == "clip_create":
            if not track.has_midi_input or slot.has_clip:
                raise ControlError("clip_create requires a MIDI track and an empty Session slot")
            def create_clip():
                slot.create_clip(op["length"])
                if "name" in op:
                    slot.clip.name = op["name"]
                if op.get("notes"):
                    slot.clip.set_notes(tuple((n["pitch"], n["start"], n["duration"], n["velocity"], n.get("mute", False)) for n in op["notes"]))
            return create_clip
        if not slot.has_clip:
            raise ControlError("The clip slot is empty; firing it could start recording")
        return slot.fire if kind == "clip_fire" else slot.stop

    def _apply(self, song, params, request_id):
        if not self.allow_writes:
            raise ControlError("Live bridge is read-only; reinstall with --allow-writes to enable edits")
        if params.get("session_id") != self.session_id:
            raise ControlError("Stale session; inspect status before editing")
        text(request_id, "request_id")
        digest = hashlib.sha256(json.dumps(params, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if request_id in self.replies:
            previous_digest, result = self.replies[request_id]
            if previous_digest != digest:
                raise ControlError("Request ID already used with different arguments")
            return result
        operations = params.get("operations")
        if not isinstance(operations, list) or not 1 <= len(operations) <= 32:
            raise ControlError("operations must contain 1..32 operations")
        for op in operations:
            validate_operation(op)
        if sum(len(op.get("notes", [])) for op in operations) > 4096:
            raise ControlError("A batch may contain at most 4096 MIDI notes in total")
        # All target handles and bounds are resolved before opening the undo step.
        plans = [self._prepare(song, op) for op in operations]
        targets = [(o["track"], o["slot"]) for o in operations if o["op"] == "clip_create"]
        if len(targets) != len(set(targets)):
            raise ControlError("A batch cannot create the same clip slot twice")
        completed = 0
        attempted = None
        error = None
        began = False
        try:
            song.begin_undo_step()
            began = True
            for i, plan in enumerate(plans):
                attempted = i
                plan()
                completed += 1
        except Exception as exc:
            error = str(exc)
        finally:
            if began:
                try:
                    song.end_undo_step()
                except Exception as exc:
                    error = error or str(exc)
        result = {"ok": error is None, "session_id": self.session_id, "request_id": request_id,
                  "completed": completed, "rolled_back": False}
        if error is not None:
            result.update({"error": error, "failed_index": attempted,
                           "outcome": "partial_or_uncertain", "retry": False,
                           "hint": "Inspect Live before further edits; use Live's Undo if appropriate"})
        self.replies[request_id] = (digest, result)
        while len(self.replies) > 256:
            self.replies.popitem(last=False)
        return result
