import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np

from rag_app.domain import Chunk


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY, body TEXT NOT NULL, vector BLOB);
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS embedding_cache(key TEXT PRIMARY KEY, vector BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, question TEXT NOT NULL, response TEXT NOT NULL, created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session, created);
                CREATE TABLE IF NOT EXISTS feedback(message TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, rating TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def replace_index(self, chunks: list[Chunk], metadata: dict, vectors=None):
        if vectors is not None:
            vectors = np.asarray(vectors, dtype=np.float32)
            if vectors.ndim != 2 or len(vectors) != len(chunks) or not np.isfinite(vectors).all():
                raise ValueError("Vector count/dimension/value không hợp lệ")
        metadata = {
            **metadata,
            "revision": str(uuid4()),
            "chunk_count": len(chunks),
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self.connect() as db:
            db.execute("DELETE FROM chunks")
            db.executemany(
                "INSERT INTO chunks VALUES(?,?,?)",
                [
                    (c.id, c.model_dump_json(), None if vectors is None else vectors[i].tobytes())
                    for i, c in enumerate(chunks)
                ],
            )
            db.execute("INSERT OR REPLACE INTO metadata VALUES('index',?)", (json.dumps(metadata),))

    def load_index(self):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT value FROM metadata WHERE key='index'").fetchone()
            rows = db.execute("SELECT body,vector FROM chunks ORDER BY id").fetchall()
        metadata = json.loads(row[0]) if row else {}
        chunks = [Chunk.model_validate_json(r[0]) for r in rows]
        vectors = None
        if rows and rows[0][1] is not None:
            vectors = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        return chunks, vectors, metadata

    def index_revision(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='index'").fetchone()
        return json.loads(row[0]).get('revision') if row else None

    def cached_vector(self, key: str):
        with self.connect() as db:
            row = db.execute("SELECT vector FROM embedding_cache WHERE key=?", (key,)).fetchone()
        return np.frombuffer(row[0], dtype=np.float32).tolist() if row else None

    def cache_vector(self, key: str, vector: list[float]):
        values = np.asarray(vector, dtype=np.float32)
        if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
            raise ValueError("Embedding không hợp lệ")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO embedding_cache VALUES(?,?)", (key, values.tobytes())
            )

    def save_message(self, owner: str, session: str, message: str, question: str, response: dict):
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            existing = db.execute("SELECT owner FROM sessions WHERE id=?", (session,)).fetchone()
            if existing and existing[0] != owner:
                raise PermissionError("Session không thuộc người dùng")
            db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?,?)", (session, owner, now))
            db.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?)",
                (message, session, question, json.dumps(response, ensure_ascii=False), now),
            )

    def session_exists(self, owner: str, session: str) -> bool:
        with self.connect() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM sessions WHERE id=? AND owner=?", (session, owner)
                ).fetchone()
            )

    def history(self, owner: str, session: str, limit: int = 50):
        if not self.session_exists(owner, session):
            raise PermissionError("Session không tồn tại hoặc không thuộc người dùng")
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,question,response,created FROM messages WHERE session=? ORDER BY rowid DESC LIMIT ?",
                (session, limit),
            ).fetchall()
        return [
            {"id": r[0], "question": r[1], "response": json.loads(r[2]), "created_at": r[3]}
            for r in reversed(rows)
        ]

    def sessions(self, owner: str):
        with self.connect() as db:
            rows = db.execute(
                "SELECT s.id,s.created,COUNT(m.id) FROM sessions s JOIN messages m ON m.session=s.id WHERE s.owner=? GROUP BY s.id ORDER BY s.created DESC LIMIT 50",
                (owner,),
            ).fetchall()
        return [{"id": r[0], "created_at": r[1], "message_count": r[2]} for r in rows]

    def delete_session(self, owner: str, session: str) -> bool:
        with self.connect() as db:
            cursor = db.execute("DELETE FROM sessions WHERE id=? AND owner=?", (session, owner))
            return bool(cursor.rowcount)

    def feedback(self, owner: str, message: str, rating: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT 1 FROM messages m JOIN sessions s ON m.session=s.id WHERE m.id=? AND s.owner=?",
                (message, owner),
            ).fetchone()
            if not row:
                return False
            db.execute("INSERT OR REPLACE INTO feedback VALUES(?,?)", (message, rating))
        return True

    def purge_history(self, days: int):
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        with self.connect() as db:
            db.execute("DELETE FROM messages WHERE created<?", (cutoff,))
            db.execute(
                "DELETE FROM sessions WHERE NOT EXISTS(SELECT 1 FROM messages WHERE session=sessions.id)"
            )
