from __future__ import annotations

import json
from pathlib import Path

from thoughtpins.memory.benchmark_datasets import benchmark_partition, load_dataset_specs, verify_dataset_file
from thoughtpins.memory.litbank_benchmark import evaluate_litbank
from thoughtpins.memory.longmemeval_benchmark import evaluate_longmemeval
from thoughtpins.memory.ranking_evidence import build_ranking_evidence
from thoughtpins.memory.search_types import SearchResult


def test_dataset_manifest_enforces_licenses_and_exclusions(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "datasets": [
                    {
                        "id": "fixture",
                        "kind": "https_file",
                        "source": "https://huggingface.co/fixture.json",
                        "revision": "a" * 64,
                        "sha256": "a" * 64,
                        "bytes": 3,
                        "license": "MIT",
                        "allowed_uses": ["calibration"],
                        "local_path": "fixture.json",
                    },
                    {
                        "id": "excluded",
                        "kind": "excluded",
                        "source": "https://example.invalid/data",
                        "revision": "unknown",
                        "license": "unverified",
                        "allowed_uses": [],
                        "local_path": "excluded",
                        "exclusion_reason": "No verified license.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    specs = load_dataset_specs(manifest)

    assert specs[0].calibration_allowed is True
    assert specs[1].allowed_uses == ()
    assert benchmark_partition("stable-case") == benchmark_partition("stable-case")
    assert verify_dataset_file(tmp_path / "missing", specs[0])


def test_ranking_evidence_projects_identity_and_scene_fields() -> None:
    result = _result("A quoted line")
    result.entity_names = ["Nora Vale"]
    result.evidence_metadata = {
        "attributed_to": "Nora Vale",
        "place": "Halcyon House",
        "provider_debug_payload": "must not affect ranking",
    }

    evidence = build_ranking_evidence(result)

    assert "Nora Vale" in evidence
    assert "Halcyon House" in evidence
    assert "provider_debug_payload" not in evidence
    assert "must not affect ranking" not in evidence


def test_longmemeval_adapter_uses_session_evidence_labels(tmp_path: Path) -> None:
    dataset = tmp_path / "long.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "question_id": "fixture-question",
                    "question_type": "single-session-user",
                    "question": "What instrument do I practice?",
                    "answer_session_ids": ["answer-session"],
                    "haystack_dates": ["2026/01/01", "2026/01/02"],
                    "haystack_session_ids": ["decoy-session", "answer-session"],
                    "haystack_sessions": [
                        [{"role": "user", "content": "I cooked lentils."}],
                        [{"role": "user", "content": "I practice the cello every evening."}],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    report = evaluate_longmemeval(dataset)

    assert report.evaluated_questions == 1
    assert report.baseline.recall_at_1 == 1.0
    assert report.thoughtpins.recall_at_1 == 1.0


def test_litbank_adapter_recalls_a_minor_speaker_from_human_attribution(tmp_path: Path) -> None:
    annotations = tmp_path / "quotes"
    annotations.mkdir()
    (annotations / "11_sample_story_brat.ann").write_text(
        "\n".join(
            [
                'QUOTE\tQ1\t0\t0\t0\t2\t" We should leave. "',
                'QUOTE\tQ2\t1\t0\t1\t2\t" I will stay. "',
                'QUOTE\tQ3\t2\t0\t2\t2\t" Come with me. "',
                "ATTRIB\tQ1\tMaya_Stone-1",
                "ATTRIB\tQ2\tEli_North-2",
                "ATTRIB\tQ3\tMaya_Stone-1",
            ]
        ),
        encoding="utf-8",
    )

    report = evaluate_litbank(annotations)

    assert report.speaker_queries == 2
    assert report.all_speakers.recall_at_1 == 1.0
    assert report.minor_speakers.recall_at_1 == 1.0


def _result(text: str) -> SearchResult:
    return SearchResult(
        memory_id="memory",
        text=text,
        memory_type="quote",
        local_date="",
        confidence="attributed_statement",
        sensitivity="personal",
        source_entry_id="entry",
        score=0.5,
        evidence_text=text,
    )
