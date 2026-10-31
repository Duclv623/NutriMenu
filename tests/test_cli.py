import json
import sys

import pytest

from rag_app import cli
from rag_app.config import Settings
from rag_app.store import Store


def test_cli_lexical_inspect_purge(tmp_path, monkeypatch, capsys):
    cfg = Settings(storage_dir=tmp_path, openai_api_key="", _env_file=None)
    monkeypatch.setattr(cli, "Settings", lambda: cfg)
    for command in (["ingest", "--mode", "lexical"], ["inspect"], ["purge-history"]):
        monkeypatch.setattr(sys, "argv", ["rag_app.cli", *command])
        cli.main()
    assert "lexical" in capsys.readouterr().out
    assert (tmp_path / "chunks.jsonl").exists()
    report = json.loads((tmp_path / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report["chunk_count"] > 0


def test_failed_hybrid_preserves_previous_index(tmp_path, monkeypatch, corpus):
    cfg = Settings(storage_dir=tmp_path, openai_api_key="", _env_file=None)
    store = Store(tmp_path / "rag.sqlite3")
    store.replace_index(corpus, {"mode": "lexical"})
    revision = store.load_index()[2]["revision"]
    monkeypatch.setattr(cli, "Settings", lambda: cfg)
    monkeypatch.setattr(sys, "argv", ["rag_app.cli", "ingest", "--mode", "hybrid"])
    with pytest.raises(RuntimeError):
        cli.main()
    assert store.load_index()[2]["revision"] == revision
