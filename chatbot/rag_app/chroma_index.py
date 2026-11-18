"""Persistent Chroma corpus and vector search over the same published revision."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np

from rag_app.domain import Chunk


class ChromaIndexError(RuntimeError):
    """The selected vector index could not be opened or queried."""


def _client(path: Path):
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as error:
        raise ChromaIndexError("Chưa cài ChromaDB. Hãy cài lại requirements.txt.") from error
    try:
        return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
    except Exception as error:
        raise ChromaIndexError("Không mở được thư mục chỉ mục ChromaDB.") from error


def _collection_identity(metadata: dict, count: int) -> tuple[str, dict]:
    try:
        revision = UUID(metadata['revision']).hex
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise ChromaIndexError("Chỉ mục nguồn thiếu phiên bản hợp lệ.") from error
    model = metadata.get('embedding_identity') or metadata.get('embedding_model')
    return f'nutriguide-{revision}', {'embedding_identity': model or 'unconfigured', 'chunk_count': count}


def _check_collection(collection, identity: dict) -> int:
    metadata = collection.metadata or {}
    dimension = metadata.get('dimension')
    metric = (collection.configuration.get('hnsw') or {}).get('space')
    if (any(metadata.get(key) != value for key, value in identity.items())
            or not isinstance(dimension, int) or dimension <= 0 or metric != 'cosine'):
        raise ChromaIndexError("Collection ChromaDB không khớp chỉ mục hoặc cấu hình cosine.")
    return dimension


class ChromaCorpus:
    ACTIVE = 'nutriguide-active'
    EMBEDDING_CACHE = 'nutriguide-embedding-cache'

    def __init__(self, path):
        self.path = path
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _client(self.path)
        return self._client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _active(self):
        from chromadb.errors import NotFoundError

        try:
            return self.client.get_collection(self.ACTIVE, embedding_function=None)
        except NotFoundError:
            return None
        except Exception as error:
            raise ChromaIndexError('Không mở được danh mục đang dùng trong ChromaDB.') from error

    def index_revision(self):
        active = self._active()
        return active.metadata['revision'] if active else None

    def replace_index(self, chunks, metadata, vectors=None, *, revision=None):
        """Switch the active collection only after the new corpus is complete."""
        metadata = {**metadata, 'revision': revision or str(uuid4()), 'chunk_count': len(chunks),
                    'created_at': datetime.now(UTC).isoformat()}
        name, identity = _collection_identity(metadata, len(chunks))
        if len({chunk.id for chunk in chunks}) != len(chunks):
            raise ValueError('Chỉ mục nguồn có ID đoạn trùng.')
        if vectors is None:
            if metadata.get('mode') == 'hybrid' and chunks:
                raise ValueError('Chỉ mục hybrid cần vector cho từng đoạn.')
            # Chroma requires an embedding for every record. Lexical snapshots
            # use a fixed placeholder and never query the vector index.
            matrix = np.ones((len(chunks), 1), dtype=np.float32)
        else:
            matrix = np.asarray(vectors, dtype=np.float32)
        if (matrix.ndim != 2 or matrix.shape[0] != len(chunks) or not matrix.shape[1]
                or not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any()):
            raise ValueError('Vector tài liệu thiếu hoặc không hợp lệ.')
        identity['dimension'] = matrix.shape[1]
        try:
            collection = self.client.create_collection(
                name=name, metadata={**identity, 'index_metadata': json.dumps(metadata, ensure_ascii=False)},
                embedding_function=None, configuration={'hnsw': {'space': 'cosine'}},
            )
            for start in range(0, len(chunks), 256):
                batch = chunks[start:start + 256]
                collection.add(
                    ids=[chunk.id for chunk in batch], embeddings=matrix[start:start + len(batch)],
                    documents=[chunk.text for chunk in batch],
                    metadatas=[{'source_id': chunk.source_id, 'section': chunk.section,
                                'chunk_metadata': chunk.model_dump_json(exclude={'text', 'id'})}
                               for chunk in batch],
                )
            if collection.count() != len(chunks):
                raise ChromaIndexError('Collection ChromaDB chưa có đủ đoạn tài liệu.')
            pointer = {'collection': name, 'revision': metadata['revision']}
            active = self.client.get_or_create_collection(self.ACTIVE, embedding_function=None, metadata=pointer)
            active.modify(metadata=pointer)
        except ChromaIndexError:
            raise
        except Exception as error:
            raise ChromaIndexError('Không ghi được kho tài liệu ChromaDB.') from error
        return name

    def load_index(self, *, include_vectors=True):
        active = self._active()
        if active is None:
            return [], None, {}
        try:
            collection = self.client.get_collection(active.metadata['collection'], embedding_function=None)
            metadata = json.loads(collection.metadata['index_metadata'])
            count = collection.count()
            if metadata['revision'] != active.metadata['revision'] or metadata['chunk_count'] != count:
                raise ChromaIndexError('Phiên bản hoặc số đoạn trong ChromaDB không khớp.')
            want_vectors = include_vectors and metadata.get('mode') == 'hybrid'
            include = ['documents', 'metadatas'] + (['embeddings'] if want_vectors else [])
            rows = []
            for offset in range(0, count, 256):
                batch = collection.get(limit=256, offset=offset, include=include)
                vectors = batch['embeddings'] if want_vectors else [None] * len(batch['ids'])
                for cid, text, fields, vector in zip(batch['ids'], batch['documents'], batch['metadatas'], vectors,
                                                      strict=True):
                    chunk = Chunk(id=cid, text=text, **json.loads(fields['chunk_metadata']))
                    rows.append((chunk, vector))
            if len(rows) != count:
                raise ChromaIndexError('Không đọc đủ đoạn tài liệu từ ChromaDB.')
            rows.sort(key=lambda pair: pair[0].id)
            matrix = np.asarray([row[1] for row in rows], dtype=np.float32) if want_vectors and rows else None
            return [row[0] for row in rows], matrix, metadata
        except ChromaIndexError:
            raise
        except Exception as error:
            raise ChromaIndexError('Không đọc được kho tài liệu ChromaDB.') from error

    def cached_vector(self, key):
        cache = self.client.get_or_create_collection(self.EMBEDDING_CACHE, embedding_function=None)
        values = cache.get(ids=[key], include=['documents'])['documents']
        return json.loads(values[0]) if values else None

    def cache_vector(self, key, vector):
        values = np.asarray(vector, dtype=np.float32)
        if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
            raise ValueError('Embedding không hợp lệ')
        cache = self.client.get_or_create_collection(self.EMBEDDING_CACHE, embedding_function=None)
        cache.upsert(ids=[key], embeddings=[[1.0]], documents=[json.dumps(values.tolist())])


class ChromaVectorIndex:
    def __init__(self, path: Path, metadata: dict, count: int, *, client=None):
        self.name, identity = _collection_identity(metadata, count)
        self._owned_client = _client(path) if client is None else None
        client = self._owned_client if client is None else client
        try:
            self.collection = client.get_collection(self.name, embedding_function=None)
            self.dimension = _check_collection(self.collection, identity)
            if self.collection.count() != count:
                raise ChromaIndexError("Collection ChromaDB chưa có đủ vector tài liệu.")
        except ChromaIndexError:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise ChromaIndexError(
                "Chưa mở được collection ChromaDB của chỉ mục hiện tại. "
                "Chạy rag_app.cli migrate-sqlite hoặc ingest --mode hybrid."
            ) from error

    def close(self):
        if self._owned_client is not None:
            self._owned_client.close()
            self._owned_client = None

    def search(self, vector, allowed_ids: list[str], limit: int) -> dict[str, float]:
        if not allowed_ids:
            return {}
        query = np.asarray(vector, dtype=np.float32)
        if (query.shape != (self.dimension,) or not np.isfinite(query).all()
                or np.linalg.norm(query) == 0):
            raise ChromaIndexError("Vector câu hỏi không khớp kích thước chỉ mục ChromaDB.")
        try:
            result = self.collection.query(
                query_embeddings=[query.tolist()], ids=allowed_ids,
                n_results=min(limit, len(allowed_ids)), include=['distances'],
            )
            return {chunk_id: 1 - float(distance) for chunk_id, distance in
                    zip(result['ids'][0], result['distances'][0], strict=True)}
        except Exception as error:
            raise ChromaIndexError("Không truy vấn được chỉ mục ChromaDB.") from error
