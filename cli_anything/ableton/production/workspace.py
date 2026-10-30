import datetime
import hashlib
import json
import os
import uuid
from pathlib import Path
from ..bridge import strict_json


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class Workspace:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Production workspace must be an existing directory")

    def path(self, relative, exists=True):
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("Use a workspace-relative path")
        target = (self.root / relative).resolve(strict=exists)
        if not target.is_relative_to(self.root):
            raise ValueError("Path escapes the production workspace")
        return target

    def state_dir(self):
        path = self.path(".ableton-harness", exists=False)
        path.mkdir(mode=0o700, exist_ok=True)
        return path

    def new_render(self):
        base = self.path("renders", exists=False)
        base.mkdir(exist_ok=True)
        path = base / (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12])
        path.mkdir(mode=0o700)
        return path

    def relative(self, path):
        return str(Path(path).resolve().relative_to(self.root))

    def read_json(self, relative):
        path = self.path(relative)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("JSON input exceeds 1 MiB")
        return strict_json(path.read_bytes())


def write_json(path, value):
    data = json.dumps(value, indent=2, allow_nan=False)
    with Path(path).open("x", encoding="utf-8") as f:
        f.write(data + "\n")
