"""Smoke test public Thought Pins hostnames after DNS and TLS are live."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    expect_text: str | None = None
    expect_json_status: str | None = None


def main() -> int:
    public_base = os.getenv("THOUGHTPINS_PUBLIC_URL", "https://thoughtpins.com").rstrip("/")
    app_base = os.getenv("THOUGHTPINS_APP_URL", "https://app.thoughtpins.com").rstrip("/")
    api_base = os.getenv("THOUGHTPINS_API_URL", "https://api.thoughtpins.com").rstrip("/")

    probes = [
        Probe("public home", f"{public_base}/", "Thought Pins"),
        Probe("privacy", f"{public_base}/privacy", "Privacy"),
        Probe("terms", f"{public_base}/terms", "Terms"),
        Probe("support", f"{public_base}/support", "Support"),
        Probe("account deletion", f"{public_base}/account/delete", "Delete Account"),
        Probe("ai disclosure", f"{public_base}/ai-disclosure", "AI Disclosure"),
        Probe("robots", f"{public_base}/robots.txt", "Sitemap:"),
        Probe("sitemap", f"{public_base}/sitemap.xml", "https://thoughtpins.com/privacy"),
        Probe("app shell", f"{app_base}/app", "Thought Pins"),
        Probe("api health", f"{api_base}/health", expect_json_status="ok"),
        Probe("api errors", f"{api_base}/v1/errors", "validation_error"),
        Probe("client config", f"{api_base}/v1/client-config", "thoughtpins.com/privacy"),
    ]

    failures: list[str] = []
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for probe in probes:
            try:
                response = client.get(probe.url)
            except Exception as exc:
                failures.append(f"{probe.name}: request failed: {exc}")
                continue
            if response.status_code != 200:
                failures.append(f"{probe.name}: expected 200, got {response.status_code}")
                continue
            if probe.expect_json_status is not None:
                try:
                    status = response.json().get("status")
                except Exception:
                    failures.append(f"{probe.name}: expected JSON response")
                    continue
                if status != probe.expect_json_status:
                    failures.append(f"{probe.name}: expected status {probe.expect_json_status!r}, got {status!r}")
            if probe.expect_text is not None and probe.expect_text not in response.text:
                failures.append(f"{probe.name}: missing text {probe.expect_text!r}")

    if failures:
        print("Public domain smoke failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Public domain smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
