"""Minimal persistent reference store. SQLite is a local/test backend, not the LMS database."""
import hashlib
import json
import re
import sqlite3

KINDS = {"standard", "decision", "course", "progress", "resource"}
GLOBAL = "shared"

def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", value):
        raise ValueError("Invalid identifier")
    return value

def text_field(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Invalid text")
    return value

class Memory:
    """Caller must authorize scope and writes. Store only non-PII methodological data."""
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS memory_v1 (
            scope TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK(revision>0), status TEXT NOT NULL
                CHECK(status IN ('draft','approved','retired')),
            title TEXT NOT NULL, content TEXT NOT NULL, digest TEXT NOT NULL,
            PRIMARY KEY(scope,kind,key,revision))""")
        self.db.commit()

    def close(self):
        self.db.close()

    def put(self, scope, kind, key, title, content, *, status, expected_revision):
        identifier(scope); identifier(key)
        if kind not in KINDS or status not in {"draft", "approved", "retired"}:
            raise ValueError("Invalid kind or status")
        text_field(title, 200); text_field(content, 20000)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision required")
        canonical = json.dumps([scope,kind,key,title,content,status], ensure_ascii=False, separators=(",",":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("""SELECT revision,digest FROM memory_v1
                WHERE scope=? AND kind=? AND key=? ORDER BY revision DESC LIMIT 1""",
                (scope,kind,key)).fetchone()
            rev = old["revision"] if old else 0
            if rev != expected_revision:
                raise ValueError("Revision conflict")
            if old and old["digest"] == digest:
                self.db.commit()
                return rev
            self.db.execute("INSERT INTO memory_v1 VALUES (?,?,?,?,?,?,?,?)",
                            (scope,kind,key,rev+1,status,title,content,digest))
            self.db.commit()
            return rev+1
        except BaseException:
            self.db.rollback()
            raise

    def current(self, scope, *, kind=None):
        identifier(scope)
        if kind is not None and kind not in KINDS:
            raise ValueError("Invalid kind")
        sql = """SELECT m.* FROM memory_v1 m WHERE m.scope IN (?,?)
            AND m.revision=(SELECT MAX(n.revision) FROM memory_v1 n
            WHERE n.scope=m.scope AND n.kind=m.kind AND n.key=m.key)
            AND m.status='approved'"""
        args = [scope, GLOBAL]
        if kind is not None:
            sql += " AND m.kind=?"; args.append(kind)
        sql += " ORDER BY m.kind,m.scope,m.key"
        return [dict(row) for row in self.db.execute(sql,args)]
