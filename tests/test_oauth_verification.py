from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa


def _rsa_fixture() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    raw_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk = json.loads(raw_jwk) if isinstance(raw_jwk, str) else raw_jwk
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    return private_key, jwk


def _configure_google(monkeypatch) -> None:
    from thoughtpins.config import config

    monkeypatch.setattr(config, "GOOGLE_OAUTH_CLIENT_IDS", ["thoughtpins-web"])
    monkeypatch.setattr(type(config), "GOOGLE_OAUTH_CLIENT_IDS", ["thoughtpins-web"])


def test_google_oauth_accepts_a_valid_cryptographically_signed_token(monkeypatch):
    from thoughtpins import oauth

    _configure_google(monkeypatch)
    private_key, jwk = _rsa_fixture()
    monkeypatch.setattr(oauth, "_fetch_jwks", lambda _url: {"keys": [jwk]})
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": "thoughtpins-web",
            "sub": "google-user-123",
            "email": "Person@Example.com",
            "email_verified": True,
            "nonce": "one-time-nonce-value",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    identity = oauth.verify_oauth_id_token("google", token)

    assert identity.subject == "google-user-123"
    assert identity.email == "person@example.com"
    assert identity.email_verified is True
    assert identity.audience == "thoughtpins-web"
    assert identity.nonce == "one-time-nonce-value"


def test_oauth_rejects_header_selected_untrusted_algorithms(monkeypatch):
    from thoughtpins import oauth

    _configure_google(monkeypatch)
    token = jwt.encode(
        {"sub": "attacker", "aud": "thoughtpins-web", "exp": int(time.time()) + 300},
        "not-a-provider-key-with-32-bytes-minimum",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(ValueError, match="algorithm is not trusted"):
        oauth.verify_oauth_id_token("google", token)


def test_oauth_requires_expiration_and_core_oidc_claims(monkeypatch):
    from thoughtpins import oauth

    _configure_google(monkeypatch)
    private_key, jwk = _rsa_fixture()
    monkeypatch.setattr(oauth, "_fetch_jwks", lambda _url: {"keys": [jwk]})
    token = jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": "thoughtpins-web",
            "sub": "google-user-123",
            "iat": int(time.time()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(ValueError, match="validation failed"):
        oauth.verify_oauth_id_token("google", token)
