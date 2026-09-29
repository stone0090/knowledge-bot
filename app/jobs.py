"""Durable single-worker inbox. SQLite and uploads live outside the Git vault."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from app.config import settings


def state_root() -> Path:
    p = Path(settings.state_path).expanduser().resolve()
    vault = Path(settings.vault_path).expanduser().resolve()
    if p == vault or vault in p.parents:
        raise RuntimeError('STATE_PATH must be outside VAULT_PATH')
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


class Inbox:
    def __init__(self):
        self.path = state_root() / 'inbox.sqlite3'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, message_id TEXT UNIQUE, scope TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, due REAL NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
                notified INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)''')
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def decode(row):
        if row is None:
            return None
        row = dict(row)
        row['payload'] = json.loads(row['payload'])
        row['result'] = json.loads(row['result'])
        return row

    def enqueue(self, message_id: str, scope: str, payload: dict):
        jid = hashlib.sha256(message_id.encode()).hexdigest()[:16]
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO jobs(id,message_id,scope,payload,created) VALUES(?,?,?,?,?)',
                       (jid, message_id, scope, json.dumps(payload, ensure_ascii=False), time.time()))
        return self.get(jid)

    def get(self, jid):
        with self.connect() as db:
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='retry',due=0 WHERE status='running'")

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status IN ('pending','retry','sync_pending') AND due<=? ORDER BY created LIMIT 1", (time.time(),)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1 WHERE id=?", (row['id'],))
        return self.get(row['id'])

    def update(self, jid, **values):
        allowed = {'status','attempts','due','result','error','notified'}
        assert set(values) <= allowed
        if 'result' in values:
            values['result'] = json.dumps(values['result'], ensure_ascii=False)
        with self.connect() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?', (*values.values(), jid))

    def retry(self, scope, jid=''):
        with self.connect() as db:
            if jid:
                row = db.execute('SELECT * FROM jobs WHERE id=? AND scope=?', (jid,scope)).fetchone()
            else:
                row = db.execute("SELECT * FROM jobs WHERE scope=? AND status IN ('failed','retry','sync_pending') ORDER BY created DESC LIMIT 1", (scope,)).fetchone()
            if not row or row['status'] not in ('failed','retry','sync_pending'):
                return None
            db.execute("UPDATE jobs SET status='pending',attempts=0,due=0,notified=0 WHERE id=?", (row['id'],))
            return row['id']

    def latest(self, scope, kind=None):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM jobs WHERE scope=? ORDER BY created DESC LIMIT 50', (scope,)).fetchall()
        for row in rows:
            job = self.decode(row)
            if kind is None or (job['payload'].get('kind') == kind and job['status'] == 'done'):
                return job
        return None

    def notifications(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute("SELECT * FROM jobs WHERE status IN ('done','failed','sync_pending') AND notified=0 ORDER BY created LIMIT 10")]
