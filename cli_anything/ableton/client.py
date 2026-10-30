"""One serialized persistent connection; never retries an uncertain request."""
import json
import os
import select
import socket
import stat
import threading
import uuid
from pathlib import Path
from .bridge import MAX_MESSAGE, strict_json
from .service import ControlError, integer


def default_config():
    configured = os.environ.get("ABLETON_CLI_CONFIG")
    if configured:
        return Path(configured).expanduser()
    library = Path.home() / ("Music/Ableton/User Library" if os.name != "nt" else "Documents/Ableton/User Library")
    return library / "Remote Scripts/CLIAnything/bridge.json"


def read_config(path):
    path = Path(path)
    try:
        info = path.stat()
        if os.name != "nt" and (stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid()):
            raise ControlError("Bridge configuration must be owned by you and mode 600")
        if info.st_size > 4096:
            raise ControlError("Bridge configuration exceeds size limit")
        config = strict_json(path.read_bytes())
    except OSError as exc:
        raise ControlError("Bridge not installed: run bridge install, then select CLIAnything in Live Preferences > Link/Tempo/MIDI") from exc
    if not isinstance(config, dict) or set(config) != {"port", "token", "allow_writes"}:
        raise ControlError("Invalid bridge configuration")
    integer(config["port"], "port", 1024, 65535)
    if not isinstance(config["token"], str) or len(config["token"]) < 32 or type(config["allow_writes"]) is not bool:
        raise ControlError("Invalid bridge token or write configuration")
    return config


class Client:
    def __init__(self, config=None, timeout=4.0):
        self.path = Path(config) if config else default_config()
        self.timeout = timeout
        self.connection = None
        self.lock = threading.Lock()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def call(self, method, params=None, request_id=None):
        with self.lock:
            config = read_config(self.path)
            try:
                if self.connection is not None:
                    readable, unused, unused2 = select.select([self.connection], [], [], 0)
                    if readable:
                        # Clean idle disconnect detected BEFORE sending anything.
                        self.close()
                if self.connection is None:
                    self.connection = socket.create_connection(("127.0.0.1", config["port"]), self.timeout)
                    self.connection.settimeout(self.timeout)
                    self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                identity = request_id or str(uuid.uuid4())
                data = json.dumps({"id": identity, "token": config["token"], "method": method,
                                   "params": params or {}}, separators=(",", ":"), allow_nan=False).encode() + b"\n"
                if len(data) > MAX_MESSAGE:
                    raise ControlError("Request exceeds 1 MiB")
                self.connection.sendall(data)
                buffer = bytearray()
                while b"\n" not in buffer:
                    chunk = self.connection.recv(65536)
                    if not chunk:
                        raise OSError("Bridge closed before responding")
                    buffer.extend(chunk)
                    if len(buffer) > MAX_MESSAGE:
                        raise ControlError("Bridge response exceeds limit")
                raw, tail = buffer.split(b"\n", 1)
                if tail:
                    raise ControlError("Unexpected data after bridge response")
                result = strict_json(raw)
                if result.get("id") != identity:
                    raise ControlError("Bridge response ID mismatch")
                if not result.get("ok"):
                    raise ControlError(result.get("error", "Bridge operation failed"))
                return result["result"]
            except (OSError, ValueError, KeyError) as exc:
                self.close()
                if isinstance(exc, ControlError):
                    raise
                raise ControlError("Live bridge unavailable or response uncertain; no retry was made. Inspect Live before retrying an edit. %s" % exc) from exc
