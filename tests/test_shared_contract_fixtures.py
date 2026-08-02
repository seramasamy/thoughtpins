"""Provider-neutral JSON fixtures stay decodable by the public contract."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_backend_models_decode_shared_fixtures() -> None:
    from thoughtpins.api_contracts import ChatResponse, ErrorEnvelope
    from thoughtpins.api_routes.entries import EntriesPageResponse, JobsPageResponse

    assert ChatResponse.model_validate(_load("chat-response.json")).status == "replied"
    assert EntriesPageResponse.model_validate(_load("entries-page.json")).items[0].user_importance == 4
    assert JobsPageResponse.model_validate(_load("jobs-page.json")).items[0].status == "completed"
    assert ErrorEnvelope.model_validate(_load("error-envelope.json")).error.code == "validation_error"


def test_first_party_clients_expose_cursor_and_idempotency_contracts() -> None:
    sources = {
        # The web client is split into endpoints and the transport beneath
        # them; these contracts are about the client's behaviour, not which
        # of the two files a given line sits in.
        "web": (
            (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
            + (ROOT / "frontend" / "src" / "api-transport.ts").read_text(encoding="utf-8")
        ),
        "web-types": (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8"),
        "ios": (
            ROOT / "mobile" / "ios" / "ThoughtPinsCore" / "Sources" / "ThoughtPinsCore" / "APIClient.swift"
        ).read_text(encoding="utf-8"),
        "ios-models": (
            ROOT / "mobile" / "ios" / "ThoughtPinsCore" / "Sources" / "ThoughtPinsCore" / "Models.swift"
        ).read_text(encoding="utf-8"),
        "android": (
            ROOT
            / "mobile"
            / "android"
            / "thoughtpins-core"
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "thoughtpins"
            / "core"
            / "ThoughtPinsApiClient.kt"
        ).read_text(encoding="utf-8"),
        "android-models": (
            ROOT
            / "mobile"
            / "android"
            / "thoughtpins-core"
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "thoughtpins"
            / "core"
            / "Models.kt"
        ).read_text(encoding="utf-8"),
    }
    assert 'headers["Idempotency-Key"]' in sources["web"]
    assert 'forHTTPHeaderField: "Idempotency-Key"' in sources["ios"]
    assert '.header("Idempotency-Key"' in sources["android"]
    assert "next_cursor" in sources["web-types"]
    assert "nextCursor" in sources["ios-models"]
    assert "nextCursor" in sources["android-models"]
