"""Account-scoped PostgreSQL conversation history."""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)


class HistoryStoreError(RuntimeError):
    pass


class PostgresHistory:
    def __init__(self, dsn, schema):
        self.dsn = dsn
        self.schema = schema

    @contextmanager
    def connect(self):
        if not self.dsn:
            raise HistoryStoreError('Cần cấu hình POSTGRES_DSN cho lịch sử chatbot.')
        try:
            with psycopg.connect(self.dsn, connect_timeout=5) as db:
                db.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(self.schema)))
                yield db
        except psycopg.Error as error:
            logger.warning('postgres_history_failed error_type=%s', type(error).__name__)
            raise HistoryStoreError('Không truy cập được lịch sử PostgreSQL của chatbot.') from None

    def initialize(self):
        with self.connect() as db:
            db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('nutriguide-history:' + self.schema,))
            db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
            db.execute('''CREATE TABLE IF NOT EXISTS sessions (
                id UUID PRIMARY KEY, owner TEXT NOT NULL, created TIMESTAMPTZ NOT NULL DEFAULT now()
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS messages (
                id UUID PRIMARY KEY, session UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                question TEXT NOT NULL, response JSONB NOT NULL, created TIMESTAMPTZ NOT NULL DEFAULT now()
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS feedback (
                message UUID PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE, rating TEXT NOT NULL
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS messages_session ON messages(session, created, id)')
            db.execute('CREATE INDEX IF NOT EXISTS sessions_owner ON sessions(owner, created)')

    def save_message(self, owner, session, message, question, response):
        with self.connect() as db:
            db.execute('INSERT INTO sessions(id,owner) VALUES (%s,%s) ON CONFLICT (id) DO NOTHING', (session, owner))
            existing = db.execute('SELECT owner FROM sessions WHERE id=%s FOR UPDATE', (session,)).fetchone()
            if not existing or existing[0] != owner:
                raise PermissionError('Session không thuộc người dùng')
            db.execute('INSERT INTO messages(id,session,question,response) VALUES (%s,%s,%s,%s)',
                       (message, session, question, Jsonb(response)))

    def session_exists(self, owner, session):
        with self.connect() as db:
            return bool(db.execute('SELECT 1 FROM sessions WHERE id=%s AND owner=%s', (session, owner)).fetchone())

    def history(self, owner, session, limit=50):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM sessions WHERE id=%s AND owner=%s', (session, owner)).fetchone():
                raise PermissionError('Session không tồn tại hoặc không thuộc người dùng')
            rows = db.execute('''SELECT m.id,m.question,m.response,m.created FROM messages m
                JOIN sessions s ON s.id=m.session WHERE s.id=%s AND s.owner=%s
                ORDER BY m.created DESC,m.id DESC LIMIT %s''', (session, owner, limit)).fetchall()
        return [{'id': str(mid), 'question': question, 'response': response,
                 'created_at': created.astimezone(UTC).isoformat()}
                for mid, question, response, created in reversed(rows)]

    def sessions(self, owner):
        with self.connect() as db:
            rows = db.execute('''SELECT s.id,s.created,COUNT(m.id) FROM sessions s JOIN messages m
                ON m.session=s.id WHERE s.owner=%s GROUP BY s.id ORDER BY s.created DESC,s.id DESC LIMIT 50''',
                              (owner,)).fetchall()
        return [{'id': str(sid), 'created_at': created.astimezone(UTC).isoformat(), 'message_count': count}
                for sid, created, count in rows]

    def delete_session(self, owner, session):
        with self.connect() as db:
            return bool(db.execute('DELETE FROM sessions WHERE id=%s AND owner=%s', (session, owner)).rowcount)

    def feedback(self, owner, message, rating):
        with self.connect() as db:
            return bool(db.execute('''INSERT INTO feedback(message,rating)
                SELECT m.id,%s FROM messages m JOIN sessions s ON s.id=m.session WHERE m.id=%s AND s.owner=%s
                ON CONFLICT (message) DO UPDATE SET rating=EXCLUDED.rating''', (rating, message, owner)).rowcount)

    def purge_history(self, days):
        cutoff = datetime.now(UTC) - timedelta(days=days)
        with self.connect() as db:
            messages = db.execute('DELETE FROM messages WHERE created<%s', (cutoff,)).rowcount
            empty = db.execute('''SELECT id FROM sessions s WHERE NOT EXISTS
                (SELECT 1 FROM messages m WHERE m.session=s.id) FOR UPDATE SKIP LOCKED''').fetchall()
            sessions = db.execute('''DELETE FROM sessions s WHERE id=ANY(%s) AND NOT EXISTS
                (SELECT 1 FROM messages m WHERE m.session=s.id)''', ([row[0] for row in empty],)).rowcount if empty else 0
        logger.info('history_purged messages_deleted=%d sessions_deleted=%d', messages, sessions)
