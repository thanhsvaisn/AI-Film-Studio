import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(os.environ.get('FILM_STUDIO_DATA', Path(__file__).resolve().parents[1] / 'data'))
ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def connection():
    db = sqlite3.connect(ROOT / 'studio.db', timeout=30)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS channels (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS youtube_uploads (project_id TEXT NOT NULL, channel_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id, channel_id))')
            db.execute('CREATE TABLE IF NOT EXISTS translation_checkpoints (project_id TEXT NOT NULL, cue_id INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id, cue_id))')
            yield db
    finally:
        db.close()


def save(project):
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO projects VALUES (?, ?)', (project['id'], json.dumps(project, ensure_ascii=False)))


def save_translation_cues(project_id, cues):
    if not cues:
        return
    with connection() as db:
        db.executemany('INSERT OR REPLACE INTO translation_checkpoints VALUES (?, ?, ?)',
                       [(project_id, cue['id'], json.dumps({k: cue[k] for k in ('text', 'translation_flags') if k in cue}, ensure_ascii=False))
                        for cue in cues])


def translation_checkpoint(project_id):
    with connection() as db:
        rows = db.execute('SELECT cue_id, payload FROM translation_checkpoints WHERE project_id=?',
                          (project_id,)).fetchall()
    return {str(cue_id): json.loads(payload) for cue_id, payload in rows}


def clear_translation_checkpoint(project_id):
    with connection() as db:
        db.execute('DELETE FROM translation_checkpoints WHERE project_id=?', (project_id,))


def get(identifier):
    with connection() as db:
        row = db.execute('SELECT payload FROM projects WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise KeyError(identifier)
    return json.loads(row[0])


def all_projects():
    with connection() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM projects ORDER BY rowid DESC')]


def save_channel(channel):
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO channels VALUES (?, ?)', (channel['id'], json.dumps(channel, ensure_ascii=False)))


def all_channels():
    with connection() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM channels ORDER BY rowid')]


def delete_channel(identifier):
    with connection() as db:
        return db.execute('DELETE FROM channels WHERE id=?', (identifier,)).rowcount


def save_upload(upload):
    with connection() as db:
        db.execute('INSERT OR REPLACE INTO youtube_uploads VALUES (?, ?, ?)',
                   (upload['project_id'], upload['channel_id'], json.dumps(upload, ensure_ascii=False)))


def get_upload(project_id, channel_id):
    with connection() as db:
        row = db.execute('SELECT payload FROM youtube_uploads WHERE project_id=? AND channel_id=?',
                         (project_id, channel_id)).fetchone()
    return json.loads(row[0]) if row else None


def project_uploads(project_id):
    with connection() as db:
        rows = db.execute('SELECT payload FROM youtube_uploads WHERE project_id=? ORDER BY rowid',
                          (project_id,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def all_uploads():
    with connection() as db:
        rows = db.execute('SELECT payload FROM youtube_uploads ORDER BY rowid').fetchall()
    return [json.loads(row[0]) for row in rows]
