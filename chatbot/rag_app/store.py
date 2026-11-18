"""Chatbot storage: Chroma corpus and account-scoped PostgreSQL history."""

from pathlib import Path

from rag_app.chroma_index import ChromaCorpus
from rag_app.history_store import PostgresHistory


class Store(ChromaCorpus):
    def __init__(self, directory: Path, *, postgres_dsn='', postgres_schema='chatbot'):
        self.directory = Path(directory)
        super().__init__(self.directory / 'chroma')
        self.history_db = PostgresHistory(postgres_dsn, postgres_schema)

    @classmethod
    def from_settings(cls, settings):
        return cls(settings.storage_dir, postgres_dsn=settings.postgres_dsn.get_secret_value(),
                   postgres_schema=settings.postgres_schema)

    def connect(self):
        return self.history_db.connect()

    def copy_index_to(self, directory):
        chunks, vectors, metadata = self.load_index()
        with Store(directory) as target:
            target.replace_index(chunks, metadata, vectors)

    def save_message(self, owner, session, message, question, response):
        return self.history_db.save_message(owner, session, message, question, response)

    def session_exists(self, owner, session):
        return self.history_db.session_exists(owner, session)

    def history(self, owner, session, limit=50):
        return self.history_db.history(owner, session, limit)

    def sessions(self, owner):
        return self.history_db.sessions(owner)

    def delete_session(self, owner, session):
        return self.history_db.delete_session(owner, session)

    def feedback(self, owner, message, rating):
        return self.history_db.feedback(owner, message, rating)

    def purge_history(self, days):
        return self.history_db.purge_history(days)
