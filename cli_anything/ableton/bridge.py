"""Bounded nonblocking TCP bridge, polled only by Live's main thread."""
import hmac
import json
import socket
import time
from .service import ControlError

MAX_MESSAGE = 1024 * 1024


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ControlError("Duplicate JSON field: " + key)
            result[key] = value
        return result
    def constant(value):
        raise ControlError("Nonfinite JSON number: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


class Bridge:
    def __init__(self, service, token, port=9877):
        if not isinstance(token, str) or len(token) < 32:
            raise ControlError("Bridge needs a private random token")
        self.service = service
        self.token = token
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server.bind(("127.0.0.1", port))
            self.server.listen(8)
            self.server.setblocking(False)
        except Exception:
            self.server.close()
            raise
        self.port = self.server.getsockname()[1]
        self.clients = {}

    def close(self):
        for connection in list(self.clients):
            self._drop(connection)
        self.server.close()

    def _drop(self, connection):
        self.clients.pop(connection, None)
        connection.close()

    def _dispatch(self, raw):
        request_id = None
        try:
            request = strict_json(raw)
            if not isinstance(request, dict) or set(request) != {"id", "token", "method", "params"}:
                raise ControlError("Invalid request envelope")
            request_id = request["id"]
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise ControlError("Invalid request ID")
            if not isinstance(request["token"], str) or not hmac.compare_digest(request["token"], self.token):
                raise ControlError("Authentication failed")
            if not isinstance(request["method"], str):
                raise ControlError("method must be a string")
            result = self.service.execute(request["method"], request["params"], request_id)
            return {"id": request_id, "ok": True, "result": result}
        except Exception as exc:
            return {"id": request_id, "ok": False, "error": str(exc)}

    def poll(self):
        # Fixed bounds on clients, bytes and requests per tick. Native Live calls
        # themselves have no hard realtime duration guarantee.
        for unused in range(4):
            try:
                connection, unused_address = self.server.accept()
            except BlockingIOError:
                break
            connection.setblocking(False)
            if len(self.clients) >= 8:
                connection.close()
            else:
                self.clients[connection] = {"input": bytearray(), "output": bytearray(),
                                            "deadline": time.monotonic() + 10}
        processed = 0
        for connection, state in list(self.clients.items()):
            try:
                if time.monotonic() > state["deadline"]:
                    self._drop(connection)
                    continue
                if state["output"]:
                    sent = connection.send(state["output"])
                    del state["output"][:sent]
                    continue
                chunk = connection.recv(65536)
                if not chunk:
                    self._drop(connection)
                    continue
                state["input"].extend(chunk)
                if len(state["input"]) > MAX_MESSAGE:
                    self._drop(connection)
                    continue
                if b"\n" in state["input"]:
                    raw, tail = state["input"].split(b"\n", 1)
                    # One outstanding request per connection: no pipelined edits.
                    if tail or processed >= 4:
                        self._drop(connection)
                        continue
                    state["input"].clear()
                    response = self._dispatch(raw)
                    encoded = json.dumps(response, separators=(",", ":"), allow_nan=False).encode() + b"\n"
                    if len(encoded) > MAX_MESSAGE:
                        encoded = json.dumps({"id": response["id"], "ok": False,
                                              "error": "Response exceeds limit; use a smaller page"}).encode() + b"\n"
                    state["output"].extend(encoded)
                    state["deadline"] = time.monotonic() + 10
                    processed += 1
                    # Reply in this tick when writable instead of imposing one
                    # extra Live update_display interval on every command.
                    sent = connection.send(state["output"])
                    del state["output"][:sent]
            except BlockingIOError:
                continue
            except (OSError, ValueError):
                self._drop(connection)
