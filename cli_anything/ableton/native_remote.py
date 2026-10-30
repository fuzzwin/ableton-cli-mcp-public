"""Installed as Remote Scripts/CLIAnything/__init__.py inside Live."""
import json
import os
from _Framework.ControlSurface import ControlSurface
from .service import Service
from .bridge import Bridge


def create_instance(c_instance):
    return CLIAnything(c_instance)


class CLIAnything(ControlSurface):
    def __init__(self, c_instance):
        super(CLIAnything, self).__init__(c_instance)
        self._bridge = None
        try:
            with open(os.path.join(os.path.dirname(__file__), "bridge.json"), "r") as handle:
                config = json.load(handle)
            self._bridge = Bridge(Service(self.song, allow_writes=config["allow_writes"]),
                                  config["token"], config["port"])
            self.log_message("CLIAnything ready on 127.0.0.1:%s" % self._bridge.port)
        except Exception as exc:
            self.log_message("CLIAnything startup failed: %s" % exc)
            self.show_message("CLIAnything could not start; inspect Log.txt")

    def update_display(self):
        super(CLIAnything, self).update_display()
        if self._bridge is not None:
            self._bridge.poll()

    def disconnect(self):
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None
        super(CLIAnything, self).disconnect()
