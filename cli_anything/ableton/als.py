"""Bounded read-only inspection of native Live sets; never writes an ALS file."""
import gzip
from pathlib import Path
from defusedxml import ElementTree
from .service import ControlError


def inspect_set(path, max_bytes=64 * 1024 * 1024):
    source = Path(path).expanduser().resolve(strict=True)
    if source.suffix.lower() != ".als" or source.stat().st_size > max_bytes:
        raise ControlError("Expected an .als file smaller than %s bytes" % max_bytes)
    try:
        with gzip.open(source, "rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ControlError("Decompressed ALS exceeds the configured limit")
        root = ElementTree.fromstring(raw)
        if root.tag != "Ableton" or root.find("LiveSet") is None:
            raise ControlError("File is not an Ableton Live set")
        tracks = []
        for item in root.findall("./LiveSet/Tracks/*"):
            name = item.find("./Name/EffectiveName")
            tracks.append({"id": item.get("Id"), "kind": item.tag,
                           "name": name.get("Value") if name is not None else None})
        tempo = root.find("./LiveSet/MasterTrack/DeviceChain/Mixer/Tempo/Manual")
        return {"path": str(source), "creator": root.get("Creator"),
                "tempo": float(tempo.get("Value")) if tempo is not None else None,
                "tracks": tracks, "read_only": True}
    except ControlError:
        raise
    except Exception as exc:
        raise ControlError("Cannot inspect ALS: %s" % exc) from exc
