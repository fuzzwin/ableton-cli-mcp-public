"""Install reviewed bridge files without modifying Live's signed app bundle."""
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from .client import default_config
from .service import ControlError, integer


def install_bridge(user_library=None, port=9877, allow_writes=False, replace=False):
    integer(port, "port", 1024, 65535)
    target = (Path(user_library).expanduser() / "Remote Scripts/CLIAnything"
              if user_library else default_config().parent)
    if target.exists() and not replace:
        raise ControlError("Bridge already exists; inspect it, then use --replace to update it")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".CLIAnything-", dir=target.parent))
    package = Path(__file__).parent
    try:
        for source, name in [("native_remote.py", "__init__.py"), ("service.py", "service.py"), ("bridge.py", "bridge.py")]:
            shutil.copyfile(package / source, stage / name)
        config = {"port": port, "token": secrets.token_urlsafe(32), "allow_writes": bool(allow_writes)}
        secret = stage / "bridge.json"
        fd = os.open(str(secret), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle)
        if target.exists():
            backup = target.with_name("CLIAnything.backup-" + secrets.token_hex(4))
            target.rename(backup)
        else:
            backup = None
        try:
            stage.rename(target)
        except Exception:
            if backup is not None:
                backup.rename(target)
            raise
        return {"installed": str(target), "config": str(target / "bridge.json"),
                "writes_enabled": bool(allow_writes), "port": port,
                "backup": str(backup) if backup else None,
                "next": "Select CLIAnything in Live Preferences > Link/Tempo/MIDI > Control Surface; Input and Output: None"}
    finally:
        if stage.exists():
            shutil.rmtree(stage)
