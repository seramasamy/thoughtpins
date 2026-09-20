import gzip
import importlib.util
import json
from pathlib import Path

from thoughtpins.memory.benchmark_model_ranking import apply_session_ranking
from thoughtpins.memory.research_budget import AttemptLedger, canonical_hash


def adapter():
    path = Path(__file__).resolve().parents[1] / "scripts/research_fireworks.py"
    spec = importlib.util.spec_from_file_location("isolated_research_fireworks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_timeout_charged_once_and_exact_order_fallback(tmp_path: Path, monkeypatch) -> None:
    module = adapter()
    (tmp_path / "responses").mkdir()
    book = AttemptLedger(tmp_path / "ledger.jsonl", cap=1, stages={"test": 1})
    count = []

    class Transport:
        def open(self, request, timeout):
            count.append(1)
            raise TimeoutError("nonsecret injected failure")

    monkeypatch.setattr(module.urllib.request, "build_opener", lambda handler: Transport())
    job = {
        "request_id": "timeout",
        "stage": "test",
        "kind": "chat",
        "data_class": "explicitly_synthetic",
        "payload": {
            "model": "accounts/fireworks/models/glm-5p3-flash",
            "max_tokens": 1536,
            "messages": [{"role": "user", "content": "Synthetic fixture"}],
        },
    }
    result = module.execute(job, "nonsecret-fixture", tmp_path, book)
    assert result["status"] == "transport_or_decode_error"
    assert module.execute(job, "nonsecret-fixture", tmp_path, book)["status"] == "already_attempted"
    assert len(count) == 1 and book.charged() > 0
    path = tmp_path / "responses" / (canonical_hash("timeout") + ".json.gz")
    record = json.load(gzip.open(path, "rt", encoding="utf-8"))
    result = apply_session_ranking(
        record.get("content"), candidate_ids=("b", "a"), baseline_ids=("a", "b"), completed=False
    )
    assert result.used_fallback and result.ranked_ids == ("a", "b")
    assert "nonsecret-fixture" not in json.dumps(record)


def test_reservations_include_completion_allowance_and_repeated_rerank_query() -> None:
    module = adapter()
    short = {"model": "accounts/fireworks/models/deepseek-v4-pro-0813", "max_tokens": 4096, "messages": []}
    long = {**short, "max_tokens": 8192}
    assert module.reservation(long, "chat") >= module.reservation(short, "chat") + 4096 * 3.96 / 1e6 - 1e-12
    rerank = {"model": "fireworks/qwen3-reranker-8b", "query": "q" * 1000, "documents": ["doc"] * 10}
    assert module.reservation(rerank, "rerank") >= 0.20 * 10000 / 1e6
    assert module.usage_cost({}, short["model"]) is None
