"""One-time, read-only import of a legacy application database."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime

import numpy as np
from psycopg.types.json import Jsonb

from rag_app.chroma_index import ChromaVectorIndex
from rag_app.domain import Chunk


def migrate_sqlite(source, store):
    if not source.is_file():
        raise ValueError('Không tìm thấy bản SQLite nguồn.')
    totals = {}
    store.history_db.initialize()
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as old:
        old.execute('BEGIN')
        # One consistent SQLite snapshot for both history and corpus.
        with store.connect() as db:
            for sid, owner, created in old.execute('SELECT id,owner,created FROM sessions'):
                db.execute('INSERT INTO sessions(id,owner,created) VALUES (%s,%s,%s) ON CONFLICT (id) DO NOTHING',
                           (sid, owner, datetime.fromisoformat(created)))
                actual = db.execute('SELECT owner FROM sessions WHERE id=%s', (sid,)).fetchone()
                if not actual or actual[0] != owner:
                    raise ValueError('Trùng mã hội thoại với chủ sở hữu khác trong PostgreSQL.')
                totals['sessions'] = totals.get('sessions', 0) + 1
            for mid, sid, question, message, created in old.execute(
                    'SELECT id,session,question,response,created FROM messages ORDER BY rowid'):
                payload = json.loads(message)
                db.execute('''INSERT INTO messages(id,session,question,response,created)
                              VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING''',
                           (mid, sid, question, Jsonb(payload), datetime.fromisoformat(created)))
                stored = db.execute('SELECT session,question,response FROM messages WHERE id=%s', (mid,)).fetchone()
                if not stored or str(stored[0]) != sid or stored[1:] != (question, payload):
                    raise ValueError('Trùng mã tin nhắn với nội dung khác trong PostgreSQL.')
                totals['messages'] = totals.get('messages', 0) + 1
            for mid, rating in old.execute('SELECT message,rating FROM feedback'):
                db.execute('INSERT INTO feedback(message,rating) VALUES (%s,%s) ON CONFLICT (message) DO NOTHING',
                           (mid, rating))
                totals['feedback'] = totals.get('feedback', 0) + 1

        for key, vector in old.execute('SELECT key,vector FROM embedding_cache'):
            store.cache_vector(key, np.frombuffer(vector, dtype=np.float32))
            totals['embedding_cache'] = totals.get('embedding_cache', 0) + 1
        row = old.execute("SELECT value FROM metadata WHERE key='index'").fetchone()
        if row and store.index_revision() is None:
            metadata = json.loads(row[0])
            rows = old.execute('SELECT body,vector FROM chunks ORDER BY id').fetchall()
            chunks = [Chunk.model_validate_json(body) for body, _ in rows]
            vectors = None
            if chunks and all(v for _, v in rows):
                vectors = np.stack([np.frombuffer(v, dtype=np.float32) for _, v in rows])
            elif chunks and metadata.get('mode') == 'hybrid':
                old_index = ChromaVectorIndex(source.parent / 'chroma', metadata, len(chunks))
                try:
                    ids = [chunk.id for chunk in chunks]
                    read = old_index.collection.get(ids=ids, include=['embeddings'])
                    by_id = dict(zip(read['ids'], read['embeddings'], strict=True))
                    vectors = np.asarray([by_id[cid] for cid in ids], dtype=np.float32)
                finally:
                    old_index.close()
            store.replace_index(chunks, metadata, vectors)
    chunks, _, _ = store.load_index(include_vectors=False)
    return {**dict.fromkeys(('sessions', 'messages', 'feedback', 'embedding_cache'), 0),
            **totals, 'chunks': len(chunks)}
