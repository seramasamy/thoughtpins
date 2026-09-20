"""Metered offline Fireworks worker. Credential enters only through getpass.

Usage: python scripts/research_fireworks.py RUN_DIRECTORY
After the hidden credential prompt, enter a registered requests/*.json filename.
One process owns the ledger; up to three requests are concurrently reserved.
"""

from __future__ import annotations

import getpass
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thoughtpins.memory.research_budget import AttemptLedger, canonical_hash  # noqa: E402

PRICES = {
    "accounts/fireworks/models/deepseek-v4-pro-0813": (1.32, 3.96),
    "accounts/fireworks/models/glm-5p3-flash": (0.15, 0.50),
    "fireworks/qwen3-embedding-8b": (0.10, 0.0),
    "fireworks/qwen3-reranker-8b": (0.20, 0.0),
}
ENDPOINTS = {"chat": "chat/completions", "embedding": "embeddings", "rerank": "rerank"}
RATE_HEADERS = (
    "X-Ratelimit-Limit-Tokens-Prompt",
    "X-Ratelimit-Limit-Tokens-Cache-Adjusted-Prompt",
    "X-Ratelimit-Limit-Tokens-Generated",
)


def rate_metadata(headers: Any) -> dict[str, float]:
    """Persist only public numeric rate limits, never arbitrary response headers."""
    result: dict[str, float] = {}
    if headers is None:
        return result
    for name in RATE_HEADERS:
        try:
            value = float(headers.get(name, ""))
            if 0 <= value < 1e15:
                result[name] = value
        except (TypeError, ValueError):
            pass
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, _fp, code, msg, headers, _newurl):
        return None


def reservation(payload: dict[str, Any], kind: str) -> float:
    """UTF-8 byte bound plus conservative template overhead, no cache savings."""
    input_price, output_price = PRICES[payload["model"]]
    if kind == "rerank":
        count = len(payload["documents"])
        bound = sum(len(x.encode()) for x in payload["documents"]) + count * (len(payload["query"].encode()) + 512)
    else:
        bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 512
        if kind == "embedding":
            bound += 64 * len(payload["input"])
    return (input_price * bound + output_price * payload.get("max_tokens", 0)) / 1e6


def usage_cost(usage: dict[str, Any], model: str) -> float | None:
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    if prompt is None or type(prompt) is not int or prompt < 0:
        return None
    output = usage.get("completion_tokens", usage.get("output_tokens", 0))
    if type(output) is not int or output < 0:
        return None
    p_in, p_out = PRICES[model]
    return (prompt * p_in + output * p_out) / 1e6


def execute(job: dict[str, Any], key: str, run: Path, ledger: AttemptLedger) -> dict[str, Any]:
    payload, kind = job["payload"], job["kind"]
    if job["data_class"] not in ("pinned_public", "explicitly_synthetic"):
        raise ValueError("Only public or synthetic data is authorized")
    if kind not in ENDPOINTS or payload["model"] not in PRICES:
        raise ValueError("Unregistered endpoint/model")
    if payload.get("n", 1) != 1 or payload.get("stream") or payload.get("service_tier", "default") != "default":
        raise ValueError("Unregistered billing parameters")
    if kind == "chat" and not 1 <= payload.get("max_tokens", 0) <= 16384:
        raise ValueError("Completion allowance must be explicitly bounded")
    if "thinking" in payload and "reasoning_effort" in payload:
        raise ValueError("Incompatible reasoning controls")
    timeout = job.get("timeout_seconds", 120)
    if not isinstance(timeout, (int, float)) or not 1 <= timeout <= 240:
        raise ValueError("Experimental timeout must be bounded")
    payload_hash = canonical_hash({"kind": kind, "payload": payload})
    request_id = job["request_id"]
    safe_id = canonical_hash(request_id)
    response_path = run / "responses" / (safe_id + ".json.gz")
    if not ledger.reserve(request_id, payload_hash=payload_hash, stage=job["stage"], amount=reservation(payload, kind)):
        return {"request_id": request_id, "status": "already_attempted", "response_exists": response_path.exists()}
    started = time.perf_counter()
    result: dict[str, Any] = {
        "request_id": request_id,
        "payload_hash": payload_hash,
        "kind": kind,
        "model": payload["model"],
        "stage": job["stage"],
        "status": "unknown",
        "usage": {},
    }
    try:
        request = urllib.request.Request(
            "https://api.fireworks.ai/inference/v1/" + ENDPOINTS[kind],
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            result["rate_limits"] = rate_metadata(response.headers)
            raw = json.load(response)
        result.update(
            status="ok", usage=raw.get("usage", {}), returned_model=raw.get("model"), provider_id=raw.get("id")
        )
        if kind == "chat":
            choice = raw.get("choices", [{}])[0]
            # Store concise requested output; omit private reasoning transcripts.
            result.update(content=choice.get("message", {}).get("content"), finish_reason=choice.get("finish_reason"))
        else:
            result["data"] = raw.get("data", raw.get("results"))
    except urllib.error.HTTPError as exc:
        # Do not persist headers, response bodies, request text or credentials.
        result.update(
            status="http_error",
            http_status=exc.code,
            error_type=type(exc).__name__,
            rate_limits=rate_metadata(exc.headers),
        )
    except (OSError, ValueError, KeyError, IndexError) as exc:
        result.update(status="transport_or_decode_error", error_type=type(exc).__name__)
    result["elapsed_seconds"] = time.perf_counter() - started
    result["actual_usd"] = usage_cost(result["usage"], payload["model"])
    response_hash = canonical_hash(result)
    temp = response_path.with_suffix(".partial")
    with gzip.open(temp, "wt", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, allow_nan=False)
    os.replace(temp, response_path)
    ledger.settle(
        request_id,
        actual=result["actual_usd"],
        status=result["status"],
        usage=result["usage"],
        response_hash=response_hash,
    )
    return {k: v for k, v in result.items() if k not in ("data", "content", "usage")}


def main() -> None:
    run = Path(sys.argv[1]).resolve()
    protocol = json.loads((run / "protocol.json").read_text())
    if protocol["total_cap_usd"] != 45:
        raise ValueError("Study cap must remain $45")
    # Kernel-owned lock releases after a crash; ledger reservations do not.
    lock = (run / "worker.lock").open("a+b")
    lock.seek(0)
    if os.name == "nt":
        import msvcrt

        if lock.read(1) == b"":
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        lock_module: Any = fcntl
        lock_module.flock(lock.fileno(), lock_module.LOCK_EX | lock_module.LOCK_NB)
    ledger = AttemptLedger(run / "budget-ledger.jsonl", cap=45, stages=protocol["budget_usd"])
    key = getpass.getpass("Fireworks credential (hidden, RAM only): ").strip()
    if not key:
        raise ValueError("Empty credential")
    print(json.dumps({"ready": True, "budget": ledger.summary()}), flush=True)
    while True:
        try:
            name = input("Batch filename or quit: ").strip()
        except EOFError:
            break
        if name == "quit":
            break
        path = (run / "requests" / name).resolve()
        if not path.is_relative_to(run / "requests") or not path.is_file():
            print("Unregistered request file", flush=True)
            continue
        jobs = json.loads(path.read_text(encoding="utf-8"))
        if len({j["request_id"] for j in jobs}) != len(jobs):
            raise ValueError("Duplicate request identities")
        # Registered transport adjustment after development rate-limit errors.
        # Failed attempts remain charged and keep their original-order fallback.
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = [pool.submit(execute, job, key, run, ledger) for job in jobs]
            for completed, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    if result["status"] not in ("ok", "already_attempted") or len(jobs) <= 6:
                        print(json.dumps(result), flush=True)
                    elif completed % 50 == 0:
                        print(
                            json.dumps(
                                {
                                    "completed": completed,
                                    "batch_jobs": len(jobs),
                                    "charged_usd": float(ledger.charged()),
                                }
                            ),
                            flush=True,
                        )
                except Exception as exc:
                    print(json.dumps({"not_sent": True, "error_type": type(exc).__name__}), flush=True)
        print(json.dumps({"batch_complete": name, "budget": ledger.summary()}), flush=True)
    key = ""
    lock.close()


if __name__ == "__main__":
    main()
