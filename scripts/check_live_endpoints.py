"""Probe the public hostnames the shipped apps actually dial.

`check_domain_readiness.py` compares strings in config files. That is worth
doing, and it is not the same question. It passed for months while
`api.thoughtpins.com` and `thoughtpins.com` had no DNS record at all, so
the iOS and Android builds carried a base URL pointing at a hostname that did
not exist — an App Review reviewer would have opened the app to
"Could not reach Thought Pins".

This is deliberately NOT part of the offline release gate: it needs the network
and would make an air-gapped build fail for reasons that are not the build's
fault. Run it before submitting, and after any DNS or hosting change.

    python scripts/check_live_endpoints.py
    python scripts/check_live_endpoints.py --json

Exit code is non-zero if any required endpoint is unreachable.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

# Cloudflare answers a bare programmatic client with a 1010 block, so probes
# carry a real browser agent. This is about reaching our own infrastructure,
# not evading anyone's rules.
BROWSER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 20

# (url, why it must work, whether a failure blocks submission)
ENDPOINTS: tuple[tuple[str, str, bool], ...] = (
    ("https://api.thoughtpins.com/v1/client-config", "the base URL compiled into both mobile apps", True),
    ("https://thoughtpins.com/", "marketing site and the root of every legal link", True),
    ("https://thoughtpins.com/privacy", "App Store privacy policy URL", True),
    ("https://thoughtpins.com/terms", "terms of use", True),
    ("https://thoughtpins.com/support", "App Store support URL, which Apple fetches", True),
    ("https://thoughtpins.com/ai-disclosure", "linked from the in-app consent screen", True),
    ("https://thoughtpins.com/account/delete", "Guideline 5.1.1(v) account deletion resource", True),
    ("https://thoughtpins.com/app", "web app advertised in the store packet", True),
)


@dataclass
class Probe:
    url: str
    reason: str
    required: bool
    host: str = ""
    resolved: list[str] = field(default_factory=list)
    status: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status is not None and 200 <= self.status < 400

    def as_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "reason": self.reason,
            "required": self.required,
            "host": self.host,
            "resolved": self.resolved,
            "status": self.status,
            "error": self.error,
            "ok": self.ok,
        }


def probe(url: str, reason: str, required: bool) -> Probe:
    result = Probe(url=url, reason=reason, required=required)
    result.host = urlparse(url).hostname or ""

    try:
        infos = socket.getaddrinfo(result.host, 443, proto=socket.IPPROTO_TCP)
        # sockaddr is (host, port) for IPv4 and (host, port, flow, scope) for
        # IPv6, so the first element is the address in both cases.
        result.resolved = sorted({str(info[4][0]) for info in infos})
    except socket.gaierror as exc:
        # The failure that actually happened. Reported on its own because a
        # missing DNS record and a 500 need completely different fixes, and
        # collapsing both into "unreachable" sends you to the wrong place.
        result.error = f"DNS does not resolve ({exc.strerror or exc})"
        return result

    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            result.status = response.status
    except urllib.error.HTTPError as exc:
        result.status = exc.code
        if not (200 <= exc.code < 400):
            result.error = f"HTTP {exc.code}"
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results.")
    args = parser.parse_args()

    results = [probe(url, reason, required) for url, reason, required in ENDPOINTS]

    if args.json:
        print(json.dumps([item.as_dict() for item in results], indent=2))
    else:
        for item in results:
            mark = "ok  " if item.ok else "FAIL"
            detail = f"HTTP {item.status}" if item.status is not None else (item.error or "no response")
            print(f"{mark} {item.url}")
            print(f"       {detail} - {item.reason}")
            if item.error and not item.resolved:
                print("       no DNS record exists for this hostname")

    blocking = [item for item in results if item.required and not item.ok]
    if not blocking:
        print("\nAll public endpoints reachable.")
        return 0

    print(f"\n{len(blocking)} required endpoint(s) unreachable:")
    for item in blocking:
        print(f"- {item.url}: {item.error or f'HTTP {item.status}'}")
    print(
        "\nA submitted app whose base URL does not answer is rejected under "
        "Guideline 2.1 before any feature is reviewed. Fix DNS and hosting "
        "before submitting."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
