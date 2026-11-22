import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np

from rag_app.config import Settings
from rag_app.legacy_migration import migrate_sqlite
from rag_app.retrieval import Retriever
from rag_app.store import Store


def test_migration_preserves_history_and_source_metadata(tmp_path, corpus):
    chunk = corpus[0]
    sid, mid = str(uuid4()), str(uuid4())
    moment = datetime.now(UTC).isoformat()
    vector = np.array([0.1, 0.5, 1], dtype=np.float32)
    source = tmp_path / 'old-app.sqlite3'
    with closing(sqlite3.connect(source)) as old, old:
        old.executescript('''
            CREATE TABLE chunks(id,body,vector);
            CREATE TABLE metadata(key,value);
            CREATE TABLE embedding_cache(key,vector);
            CREATE TABLE sessions(id,owner,created);
            CREATE TABLE messages(id,session,question,response,created);
            CREATE TABLE feedback(message,rating);
        ''')
        old.execute('INSERT INTO chunks VALUES (?,?,?)', (chunk.id, chunk.model_dump_json(), vector.tobytes()))
        old.execute('INSERT INTO metadata VALUES (?,?)', ('index', json.dumps({
            'revision': str(uuid4()), 'mode': 'hybrid', 'embedding_identity': 'migration-check',
        })))
        old.execute('INSERT INTO embedding_cache VALUES (?,?)', ('cache-key', vector.tobytes()))
        old.execute('INSERT INTO sessions VALUES (?,?,?)', (sid, 'dev:migration-test', moment))
        old.execute('INSERT INTO messages VALUES (?,?,?,?,?)', (mid, sid, 'Nguồn ở đâu?', '{}', moment))
        old.execute('INSERT INTO feedback VALUES (?,?)', (mid, 'helpful'))

    cfg = Settings(storage_dir=tmp_path / 'target', _env_file=None)
    store = Store.from_settings(cfg)
    assert migrate_sqlite(source, store) == {
        'chunks': 1, 'sessions': 1, 'messages': 1, 'feedback': 1, 'embedding_cache': 1,
    }
    revision = store.index_revision()
    migrate_sqlite(source, store)
    assert store.index_revision() == revision
    assert store.sessions('dev:migration-test')[0]['message_count'] == 1
    assert not store.sessions('dev:another-account')
    assert store.history('dev:migration-test', sid)[0]['question'] == 'Nguồn ở đâu?'
    with store.connect() as db:
        assert db.execute('SELECT rating FROM feedback WHERE message=%s', (mid,)).fetchone() == ('helpful',)

    source.rename(tmp_path / 'backup.sqlite3')
    retriever = Retriever(Store.from_settings(cfg), chroma_path=store.path)
    assert retriever.chunks == [chunk]
    assert retriever.chroma.search(vector, [chunk.id], 1)[chunk.id] > .99
    assert store.cached_vector('cache-key') == vector.tolist()
