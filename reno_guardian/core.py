"""Durable incidents and approval records, separate from the ERP database."""
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def redact(text):
    text = re.sub(r"(?i)(authorization|password|token|api[_-]?key|secret)([\s:=]+)[^\s,;]+",
                  r"\1\2[REDACTED]", str(text))
    return re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)[:12000]


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, title TEXT,
                    evidence TEXT, severity TEXT, state TEXT, updated REAL,
                    occurrences INTEGER, notified REAL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY, incident INTEGER, content TEXT, digest TEXT,
                    expires REAL, state TEXT DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, at REAL, action TEXT, detail TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, fingerprint, title, evidence, severity):
        with self.connect() as db:
            db.execute("""INSERT INTO incidents
                (fingerprint,title,evidence,severity,state,updated,occurrences)
                VALUES (?,?,?,?,'open',?,1)
                ON CONFLICT(fingerprint) DO UPDATE SET title=excluded.title,
                evidence=excluded.evidence,severity=excluded.severity,state='open',
                updated=excluded.updated,occurrences=occurrences+1,
                notified=CASE WHEN incidents.state='resolved' THEN 0 ELSE incidents.notified END""",
                       (fingerprint, redact(title), redact(evidence), severity, time.time()))
            return dict(db.execute("SELECT * FROM incidents WHERE fingerprint=?", (fingerprint,)).fetchone())

    def resolve(self, fingerprint):
        with self.connect() as db:
            db.execute("UPDATE incidents SET state='resolved',updated=? WHERE fingerprint=?",
                       (time.time(), fingerprint))

    def incidents(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM incidents ORDER BY updated DESC LIMIT 200")]

    def incident(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT * FROM incidents WHERE id=?", (ident,)).fetchone()
            if not row:
                raise ValueError("Incident not found")
            return dict(row)

    def audit(self, action, detail):
        with self.connect() as db:
            db.execute("INSERT INTO audit(at,action,detail) VALUES(?,?,?)",
                       (time.time(), action, redact(detail)))

    def reserve_call(self, ident):
        # Reserve before making a paid external request. Ambiguous timeouts
        # are left for operator review instead of risking duplicate calls.
        with self.connect() as db:
            result = db.execute("""UPDATE incidents SET notified=? WHERE id=?
                AND state='open' AND severity='critical' AND notified=0""", (time.time(), ident))
            return result.rowcount == 1

    def propose(self, ident, content):
        self.incident(ident)
        content = redact(content)
        digest = hashlib.sha256(content.encode()).hexdigest()
        with self.connect() as db:
            db.execute("UPDATE proposals SET state='superseded' WHERE incident=? AND state IN ('pending','approved')", (ident,))
            result = db.execute("INSERT INTO proposals(incident,content,digest,expires) VALUES(?,?,?,?)",
                                (ident, content, digest, time.time()+3600))
            return {"id": result.lastrowid, "digest": digest, "content": content}

    def approve(self, ident, digest):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM proposals WHERE id=?", (ident,)).fetchone()
            if not row or row["state"] != "pending" or row["expires"] < time.time() or row["digest"] != digest:
                raise ValueError("Proposal expired, changed or already processed")
            if db.execute("SELECT state FROM incidents WHERE id=?", (row["incident"],)).fetchone()[0] != "open":
                raise ValueError("Incident has resolved")
            db.execute("UPDATE proposals SET state='approved' WHERE id=?", (ident,))
            db.execute("INSERT INTO audit(at,action,detail) VALUES(?,?,?)",
                       (time.time(), "approve", f"proposal={ident} digest={digest}"))
            return {"state": "approved", "execution": "requires configured deployment integration"}
