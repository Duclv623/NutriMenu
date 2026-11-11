"""Persistent Chroma search over vectors created by the configured embedding provider."""

from pathlib import Path
from uuid import UUID

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
    if not model or not count or metadata.get('mode') != 'hybrid':
        raise ChromaIndexError("ChromaDB cần chỉ mục hybrid có thông tin model embedding.")
    return f'nutriguide-{revision}', {'embedding_identity': model, 'chunk_count': count}


def _check_collection(collection, identity: dict) -> int:
    metadata = collection.metadata or {}
    dimension = metadata.get('dimension')
    metric = (collection.configuration.get('hnsw') or {}).get('space')
    if (any(metadata.get(key) != value for key, value in identity.items())
            or not isinstance(dimension, int) or dimension <= 0 or metric != 'cosine'):
        raise ChromaIndexError("Collection ChromaDB không khớp chỉ mục hoặc cấu hình cosine.")
    return dimension


def write_chroma_index(path: Path, chunks: list[Chunk], vectors, metadata: dict) -> str:
    """Publish vectors for a single immutable corpus revision, without embedding again."""
    name, identity = _collection_identity(metadata, len(chunks))
    matrix = np.asarray(vectors, dtype=np.float32)
    if (matrix.ndim != 2 or matrix.shape[0] != len(chunks) or not matrix.shape[1]
            or not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any()):
        raise ChromaIndexError("Vector tài liệu thiếu hoặc không hợp lệ.")
    if len({chunk.id for chunk in chunks}) != len(chunks):
        raise ChromaIndexError("Chỉ mục nguồn có ID đoạn trùng.")
    identity['dimension'] = matrix.shape[1]
    client = _client(path)
    try:
        collection = client.get_or_create_collection(
            name=name, metadata=identity, embedding_function=None,
            configuration={'hnsw': {'space': 'cosine'}},
        )
        _check_collection(collection, identity)
        for start in range(0, len(chunks), 256):
            batch = chunks[start:start + 256]
            collection.upsert(
                ids=[chunk.id for chunk in batch], embeddings=matrix[start:start + len(batch)],
                documents=[chunk.text for chunk in batch],
                metadatas=[{'source_id': chunk.source_id, 'section': chunk.section} for chunk in batch],
            )
        if collection.count() != len(chunks):
            raise ChromaIndexError("Số vector trong ChromaDB không khớp số đoạn nguồn.")
    except ChromaIndexError:
        raise
    except Exception as error:
        raise ChromaIndexError("Không ghi được chỉ mục vector vào ChromaDB.") from error
    return name


class ChromaVectorIndex:
    def __init__(self, path: Path, metadata: dict, count: int):
        self.name, identity = _collection_identity(metadata, count)
        client = _client(path)
        try:
            self.collection = client.get_collection(self.name, embedding_function=None)
            self.dimension = _check_collection(self.collection, identity)
            if self.collection.count() != count:
                raise ChromaIndexError("Collection ChromaDB chưa có đủ vector tài liệu.")
        except ChromaIndexError:
            raise
        except Exception as error:
            raise ChromaIndexError(
                "Chưa mở được collection ChromaDB của chỉ mục hiện tại. "
                "Chạy rag_app.cli import-chroma hoặc ingest --mode hybrid."
            ) from error

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
