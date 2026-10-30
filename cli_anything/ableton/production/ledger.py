"""Local append-only records for retrieval; never model training."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from .workspace import timestamp


class Ledger:
    def __init__(self, workspace):
        self.path = workspace.state_dir() / "evidence.sqlite3"
        if self.path.is_symlink():
            raise ValueError("Ledger may not be a symlink")
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, created TEXT NOT NULL, kind TEXT NOT NULL, tags TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, kind, tags, payload):
        if kind not in {"analysis", "render", "plugin_probe", "feedback", "review"}:
            raise ValueError("Unsupported evidence kind")
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or not t or len(t) > 80 for t in tags):
            raise ValueError("Use at most 20 short text tags")
        text = json.dumps(payload, sort_keys=True, allow_nan=False)
        if len(text.encode()) > 256 * 1024:
            raise ValueError("Evidence exceeds 256 KiB")
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (identity, timestamp(), kind, json.dumps(tags), text, hashlib.sha256(text.encode()).hexdigest()))
        return identity

    def feedback(self, event_id, verdict, note, tags):
        if verdict not in {"prefer", "reject", "needs_work"} or not isinstance(note, str) or not 1 <= len(note) <= 2000:
            raise ValueError("Feedback needs prefer/reject/needs_work and a 1..2000 character note")
        with self.connect() as db:
            target = db.execute("SELECT kind FROM events WHERE id=?", (event_id,)).fetchone()
        if target is None or target[0] == "feedback":
            raise ValueError("Feedback must refer to an existing non-feedback event")
        return self.append("feedback", tags, {"event_id": event_id, "verdict": verdict, "note": note,
                                                  "evidence_type": "explicit_user_feedback"})

    def recall(self, query="", limit=20):
        if type(limit) is not int or not 1 <= limit <= 50 or len(query) > 200:
            raise ValueError("Recall limit 1..50; query at most 200 characters")
        with self.connect() as db:
            # Literal matching: user text cannot become a SQL expression or wildcard.
            rows = db.execute("SELECT id,created,kind,tags,payload,sha256 FROM events WHERE instr(lower(tags || payload), lower(?)) > 0 ORDER BY rowid DESC LIMIT ?", (query, limit)).fetchall()
        return {"events": [{"id": r[0], "created": r[1], "kind": r[2], "tags": json.loads(r[3]),
                            "payload": json.loads(r[4]), "sha256": r[5]} for r in rows],
                "limit": "Retrieved local evidence and user feedback; no model training or automatic subjective acceptance."}
