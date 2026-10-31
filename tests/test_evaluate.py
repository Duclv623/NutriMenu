import pytest

from rag_app.config import Settings
from rag_app.evaluate import evaluate


def test_lexical_evaluation_metrics_are_bounded(system):
    report = evaluate(system.cfg)
    assert report["knowledge_cases"] == 20 and len(report["routing"]) == 40
    for key in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr_at_5", "router_accuracy"):
        assert 0 <= report[key] <= 1
    assert not report["llm_answer_quality_evaluated"]
    assert not report["unanswerable_generation_evaluated"]


def test_evaluation_no_index_or_unbuilt_dense(tmp_path, system):
    with pytest.raises(ValueError):
        evaluate(Settings(storage_dir=tmp_path / "empty", _env_file=None))
    with pytest.raises(ValueError):
        evaluate(system.cfg, "dense")
