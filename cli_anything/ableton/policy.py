"""Shared silent-default policy, enforced before native calls."""
from .service import ControlError


def guard_playback(operations, allow_playback=False):
    if allow_playback:
        return
    for operation in operations:
        if operation.get("op") == "clip_fire" or (operation.get("op") == "transport" and operation.get("action") == "play"):
            raise ControlError("Silent mode blocks playback and clip launch. Explicit --allow-playback is required.")
