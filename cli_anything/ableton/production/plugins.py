"""Metadata inventory first; explicit file-only probes in a child process."""
import hashlib
import json
import os
import platform
import plistlib
import struct
import subprocess
import sys
import uuid
from pathlib import Path
from .workspace import digest, timestamp, write_json
from .ledger import Ledger
from .progress import checkpoint

ROOTS = [Path("/Library/Audio/Plug-Ins"), Path.home() / "Library/Audio/Plug-Ins"]
FORMATS = {".vst3": "VST3", ".component": "AU", ".vst": "VST2"}


def architectures(path):
    names = {7: "i386", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "arm64"}
    try:
        with path.open("rb") as f:
            data = f.read(4096)
        if data[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
            count = min(struct.unpack_from(">I", data, 4)[0], 16)
            stride = 32 if data[3] == 191 else 20
            return [names.get(struct.unpack_from(">I", data, 8 + i * stride)[0], "unknown") for i in range(count)]
        endian = "<" if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe") else ">"
        if data[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"):
            return [names.get(struct.unpack_from(endian + "I", data, 4)[0], "unknown")]
    except (OSError, struct.error):
        pass
    return []


def describe(path):
    path = Path(path).resolve()
    plist = path / "Contents/Info.plist"
    metadata, error = {}, None
    try:
        if plist.stat().st_size > 1024 * 1024:
            raise ValueError("Bundle metadata exceeds 1 MiB")
        metadata = plistlib.loads(plist.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        error = str(exc)
    executable = path / "Contents/MacOS" / str(metadata.get("CFBundleExecutable", ""))
    executable_stat = None
    if executable.is_file() and executable.resolve().is_relative_to(path):
        st = executable.stat()
        executable_stat = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
    signature = {"plist_sha256": digest(plist) if plist.is_file() and plist.stat().st_size <= 1024 * 1024 else None,
                 "executable_stat": executable_stat}
    return {"id": hashlib.sha256(str(path).encode()).hexdigest()[:20], "name": metadata.get("CFBundleName", path.stem),
            "path": str(path), "format": FORMATS[path.suffix.lower()],
            "bundle_id": metadata.get("CFBundleIdentifier"),
            "version": metadata.get("CFBundleShortVersionString", metadata.get("CFBundleVersion")),
            "architectures": architectures(executable) if executable_stat else [],
            "metadata_fingerprint": hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest(),
            "metadata_error": error, "offline_status": "untested", "live_status": "unverified"}


def scan(roots=None):
    found = []
    for root in ROOTS if roots is None else roots:
        root = Path(root)
        if not root.exists():
            continue
        for base, dirs, files in os.walk(root, followlinks=False):
            if len(Path(base).relative_to(root).parts) > 3:
                dirs[:] = []
                continue
            for name in list(dirs):
                if Path(name).suffix.lower() in FORMATS:
                    dirs.remove(name)
                    found.append(describe(Path(base) / name))
                    if len(found) >= 2000:
                        raise ValueError("Plugin inventory exceeds 2000 bundles")
    # Roots can overlap; never count a bundle twice.
    found = list({item["id"]: item for item in found}.values())
    return {"schema_version": 1, "scanned": timestamp(), "host_architecture": platform.machine(),
            "plugins": sorted(found, key=lambda p: (p["name"].lower(), p["format"])),
            "loaded_plugins": 0, "limit": "Metadata only. Fingerprint uses plist hash and executable size/mtime, not a binary attestation. Installed does not mean licensed or renderable."}


def inventory(workspace, refresh=False):
    path = workspace.state_dir() / "plugins.json"
    if path.is_symlink():
        raise ValueError("Inventory may not be a symlink")
    old = json.loads(path.read_text()) if path.exists() else None
    if not refresh and old:
        return old
    current = scan()
    # Keep successful and failed observations only when the recorded metadata still matches.
    previous = {p["id"]: p for p in (old or {}).get("plugins", [])}
    for p in current["plugins"]:
        before = previous.get(p["id"], {})
        probe = before.get("probe", {})
        try:
            from importlib.metadata import version
            current_host = "pedalboard " + version("pedalboard")
        except Exception:
            current_host = None
        if (before.get("metadata_fingerprint") == p["metadata_fingerprint"] and probe
                and probe.get("architecture") == platform.machine()
                and probe.get("host") == current_host
                and probe.get("python") == platform.python_version()):
            p["offline_status"], p["probe"] = before["offline_status"], before["probe"]
        design=before.get("design_evidence",{})
        if (before.get("metadata_fingerprint")==p["metadata_fingerprint"] and design
                and design.get("architecture")==platform.machine() and design.get("host")==current_host
                and design.get("python")==platform.python_version()):
            p["design_evidence"]=design
    tmp = path.with_name("plugins-" + uuid.uuid4().hex + ".tmp")
    write_json(tmp, current)
    os.replace(tmp, path)
    return current


def probe(workspace, plugin_id):
    from .audio import dependencies
    dependencies()
    from importlib.metadata import version
    data = inventory(workspace)
    plugin = next((p for p in data["plugins"] if p["id"] == plugin_id), None)
    if plugin is None:
        raise ValueError("Unknown plugin ID; scan inventory first")
    path = Path(plugin["path"]).resolve()
    if not any(path.is_relative_to(r.resolve()) for r in ROOTS):
        raise ValueError("Plugin must reside in a standard system/user plugin directory")
    if plugin["format"] == "VST2":
        raise ValueError("This offline host supports VST3 and AU; VST2 remains unverified")
    if describe(path)["metadata_fingerprint"] != plugin["metadata_fingerprint"]:
        raise ValueError("Plugin changed; refresh inventory before probing")
    output = workspace.new_render()
    result_path = output / "probe-result.json"
    checkpoint("render")
    with (output / "host.log").open("wb") as log:
        try:
            proc = subprocess.run([sys.executable, "-m", "cli_anything.ableton.production.probe_worker", str(path), str(output)],
                                  stdout=log, stderr=log, timeout=45, shell=False)
            result = json.loads(result_path.read_text()) if result_path.exists() else {"status": "load_error", "reason": "Child exited without a result", "exit_code": proc.returncode}
        except subprocess.TimeoutExpired:
            result = {"status": "timeout", "reason": "Explicit probe exceeded 45 seconds"}
    result.update({"plugin_id": plugin_id, "metadata_fingerprint": plugin["metadata_fingerprint"],
                   "created": timestamp(), "host": "pedalboard " + version("pedalboard"),
                   "python": platform.python_version(), "architecture": platform.machine(),
                   "output_directory": workspace.relative(output), "speaker_playback": False,
                   "live_status": "unverified", "scope": "Default-state note/chord or test-noise render only; not every preset or native Live compatibility."})
    checkpoint("record")
    plugin.update(offline_status=result["status"], probe=result)
    target = workspace.state_dir() / "plugins.json"
    tmp = target.with_name("plugins-" + uuid.uuid4().hex + ".tmp")
    write_json(tmp, data)
    os.replace(tmp, target)
    event_id = Ledger(workspace).append("plugin_probe", [plugin["name"], plugin["format"]], result)
    return {"event_id": event_id, **result}
