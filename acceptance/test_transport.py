import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from cli_anything.ableton.bridge import Bridge, MAX_MESSAGE
from cli_anything.ableton.client import Client, read_config
from cli_anything.ableton.install import install_bridge
from cli_anything.ableton.service import Service, ControlError
from test_contract import song_fixture


class RunningBridge:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bridge.json"
        self.song = song_fixture()
        self.bridge = Bridge(Service(lambda: self.song, allow_writes=True), "x" * 48, port=0)
        self.path.write_text(json.dumps({"port": self.bridge.port, "token": "x" * 48, "allow_writes": True}))
        self.path.chmod(0o600)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            self.bridge.poll()
            self.stop.wait(0.001)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.bridge.close()
        self.tmp.cleanup()


class Transport(unittest.TestCase):
    def setUp(self):
        self.server = RunningBridge()
        self.client = Client(self.server.path)

    def tearDown(self):
        self.client.close()
        self.server.close()

    def test_authentication_and_loopback(self):
        self.assertEqual(self.server.bridge.server.getsockname()[0], "127.0.0.1")
        config = json.loads(self.server.path.read_text())
        config["token"] = "wrong" * 10
        self.server.path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ControlError, "Authentication"):
            self.client.call("status")

    def test_persistent_connection_and_batch(self):
        status = self.client.call("status")
        first = self.client.connection
        self.client.call("tracks")
        self.assertIs(first, self.client.connection)
        response = self.client.call("apply", {"session_id": status["session_id"],
                                              "operations": [{"op": "tempo", "bpm": 123}]})
        self.assertTrue(response["ok"])
        self.assertEqual(self.client.call("status")["tempo"], 123)

    def test_insecure_config_rejected(self):
        self.server.path.chmod(0o644)
        with self.assertRaisesRegex(ControlError, "mode 600"):
            read_config(self.server.path)

    def test_duplicate_and_nonfinite_json(self):
        for raw in [b'{"id":"a","id":"b"}', b'{"number":NaN}']:
            with socket.create_connection(("127.0.0.1", self.server.bridge.port), 1) as conn:
                conn.sendall(raw + b"\n")
                response = json.loads(conn.makefile("rb").readline())
                self.assertFalse(response["ok"])

    def test_oversize_disconnect(self):
        with socket.create_connection(("127.0.0.1", self.server.bridge.port), 2) as conn:
            conn.sendall(b"x" * (MAX_MESSAGE + 1))
            try:
                self.assertEqual(conn.recv(1), b"")
            except ConnectionResetError:
                pass

    def test_installer_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = install_bridge(tmp)
            target = Path(first["installed"])
            original = (target / "bridge.json").read_bytes()
            self.assertEqual((target / "bridge.json").stat().st_mode & 0o777, 0o600)
            self.assertFalse(first["writes_enabled"])
            with self.assertRaises(ControlError):
                install_bridge(tmp)
            self.assertEqual((target / "bridge.json").read_bytes(), original)
            second = install_bridge(tmp, replace=True)
            self.assertEqual((Path(second["backup"]) / "bridge.json").read_bytes(), original)

    def test_uncertain_mutation_is_not_retried(self):
        # A native operation outlives the client's deadline. Only one request is
        # sent; the caller receives an uncertain outcome and must inspect Live.
        original = self.server.bridge.service.execute
        calls = []
        def delayed(method, params, request_id):
            calls.append(method)
            time.sleep(0.03)
            return original(method, params, request_id)
        self.server.bridge.service.execute = delayed
        self.client.timeout = 0.005
        with self.assertRaisesRegex(ControlError, "no retry"):
            self.client.call("status")
        self.server.stop.wait(0.05)
        self.assertEqual(calls, ["status"])
