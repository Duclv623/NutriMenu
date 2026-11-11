import argparse
import json
import sys
from uuid import uuid4

from rag_app.chroma_index import ChromaIndexError, ChromaVectorIndex, write_chroma_index
from rag_app.config import Settings
from rag_app.ingestion import build_chunks
from rag_app.provider import create_provider, embed_chunks
from rag_app.store import Store


def main():
    parser = argparse.ArgumentParser(
        description="Quản lý corpus đã duyệt; không index PDF tùy tiện"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--mode", choices=["lexical", "hybrid"], default="hybrid")
    sub.add_parser("import-chroma", help="Sao chép vector hybrid đã có sang ChromaDB")
    sub.add_parser("inspect")
    sub.add_parser("purge-history")
    args = parser.parse_args()
    settings = Settings()
    store = Store(settings.storage_dir / "rag.sqlite3")
    if args.command == "ingest":
        chunks, report = build_chunks(settings)
        vectors = None
        if args.mode == "hybrid":
            provider = create_provider(settings)
            try:
                vectors = embed_chunks(provider, store, chunks, settings.embedding_identity)
            finally:
                provider.close()
        metadata = {
            **report,
            "mode": args.mode,
            "embedding_model": settings.active_embedding_model if vectors is not None else None,
            "embedding_identity": settings.embedding_identity if vectors is not None else None,
            "embedding_provider": settings.embedding_mode if vectors is not None else None,
        }
        revision = None
        if vectors is not None and settings.vector_backend == "chroma":
            revision = str(uuid4())
            write_chroma_index(settings.storage_dir / "chroma", chunks, vectors, {**metadata, 'revision': revision})
            vectors = None
        store.replace_index(chunks, metadata, vectors, revision=revision)
        # Public document text only. No credentials or chat messages in this export.
        (settings.storage_dir / "chunks.jsonl").write_text(
            "\n".join(c.model_dump_json() for c in chunks) + "\n", encoding="utf-8"
        )
        (settings.storage_dir / "ingestion_report.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
    elif args.command == "import-chroma":
        chunks, vectors, metadata = store.load_index()
        identity = metadata.get("embedding_identity", metadata.get("embedding_model"))
        if metadata.get("mode") != "hybrid" or identity != settings.embedding_identity:
            raise ChromaIndexError("Cần chỉ mục hybrid cùng cấu hình embedding để nhập vào ChromaDB.")
        path = settings.storage_dir / "chroma"
        if vectors is not None:
            collection = write_chroma_index(path, chunks, vectors, metadata)
        else:
            collection = ChromaVectorIndex(path, metadata, len(chunks)).name
        print(json.dumps({"collection": collection, "chunk_count": len(chunks)}, ensure_ascii=False))
    elif args.command == "inspect":
        chunks, _, metadata = store.load_index(include_vectors=False)
        print(
            json.dumps(
                {
                    "chunk_count": len(chunks),
                    "vector_backend": settings.vector_backend,
                    "metadata": metadata,
                    "provider_configured": settings.has_key,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        store.purge_history(settings.history_retention_days)
        print("Đã xóa lịch sử quá hạn theo cấu hình")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Errors in the app are sanitized before reaching this boundary.
        print(f"Không hoàn thành: {error}", file=sys.stderr)
        sys.exit(1)
