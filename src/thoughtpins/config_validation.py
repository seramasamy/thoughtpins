"""Rules about which configuration combinations may serve real traffic.

Separated from `config.py` so the module that defines settings does not also
carry the policy about how they may be combined. Each function takes the values
it judges rather than reading them, so a caller can ask the question about a
hypothetical configuration — which is what the tests do.
"""

from __future__ import annotations

from collections.abc import Iterable


def graph_backend_problems(provider: str, shadow_enabled: bool) -> list[str]:
    """Return privacy blockers for auxiliary graph backends."""

    if provider == "internal_sql" and not shadow_enabled:
        return []
    return [
        "External graph backends are evaluation-only until tenant-scoped account deletion is verified; "
        "use GRAPH_PROVIDER=internal_sql and GRAPH_SHADOW_ENABLED=false in production."
    ]


def llm_pricing_problems(models: Iterable[str]) -> list[str]:
    """Refuse to serve on a spend cap that cannot match the provider bill.

    The cap in `usage.py` is only as honest as the price map behind it. An
    unpriced runtime meters at `LLM_DEFAULT_*`, and if the real model costs more,
    spend runs past the cap by that multiple before anything stops it — a
    frontier open model at $3/$15 against the $0.30/$1.20 default overshoots
    tenfold. That is a budget reporting headroom while the balance drains, so it
    is a startup failure rather than a warning.

    Names are normalised first, because the client requests the normalised form
    and metering falls back to it. Pricing the display label "model[variant]"
    while the request sends "model" would validate cleanly and still meter at
    the default.

    This closes the deterministic half only. Usage is recorded against the name
    the provider echoes in its response, falling back to the requested one, and
    an echoed name is not knowable before a call. Where they differ, the runtime
    warning in `usage.py` is the remaining signal.
    """
    from thoughtpins.llm.client import normalize_llm_model_name
    from thoughtpins.usage import is_priced

    unpriced = sorted(
        {
            normalize_llm_model_name(model)
            for model in models
            if model and not is_priced(normalize_llm_model_name(model))
        }
    )
    if not unpriced:
        return []
    return [
        "LLM_PRICING_JSON must carry input_per_1m and output_per_1m for every configured "
        f"runtime; {len(unpriced)} of them are unpriced and would meter at the default rate, "
        "so USAGE_MONTHLY_BUDGET_USD would not match what the provider actually charges."
    ]
