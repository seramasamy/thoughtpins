"""Conservative recovery for explicit expenses and reminder requests."""

from __future__ import annotations

import re

from loguru import logger

from thoughtpins.llm import ExtractedActionItem, ExtractedExpense, ExtractionResult

_MONEY_RE = re.compile(r"\$(?P<amount>\d{1,7}(?:\.\d{1,2})?)")
_PURCHASE_CUE_RE = re.compile(r"\b(?:bought|charged|cost|ordered|paid|picked up|purchased|spent)\b", re.IGNORECASE)
_MERCHANT_RE = re.compile(r"\b(?:at|from)\s+(?P<merchant>[A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*){0,3})")
_REASON_AFTER_AMOUNT_RE = re.compile(r"\b(?:on|for)\s+(?P<reason>[^.!?]{1,100})", re.IGNORECASE)
_REASON_BEFORE_MERCHANT_RE = re.compile(
    r"\b(?:bought|ordered|picked up|purchased)\s+(?P<reason>[^.!?]{1,100}?)\s+"
    r"(?:at|from)\s+[A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*){0,3}\s+(?:for\s*)?$",
    re.IGNORECASE,
)
_REMINDER_RE = re.compile(
    r"(?:(?P<before>\b(?:today|tonight|tomorrow|next\s+(?:week|month))"
    r"(?:\s+at\s+(?:[01]?\d(?::[0-5]\d)?\s*(?:am|pm)|2[0-3]:[0-5]\d))?)\s*,?\s*)?"
    r"\bremind\s+(?P<owner>me|myself|[A-Za-z][A-Za-z'-]{1,50})\s+"
    r"(?:(?P<after>\b(?:today|tonight|tomorrow|next\s+(?:week|month))"
    r"(?:\s+at\s+(?:[01]?\d(?::[0-5]\d)?\s*(?:am|pm)|2[0-3]:[0-5]\d))?)\s+)?"
    r"to\s+(?P<description>[^.!?\n]{2,240})",
    re.IGNORECASE,
)
_DIRECT_REQUEST_PREFIX_RE = re.compile(
    r"^(?:please|(?:can|could|would|will)\s+you|i\s+(?:need|want)\s+you\s+to|hey(?:\s+thought\s+pins)?)?$",
    re.IGNORECASE,
)
_COORDINATED_TASK_RE = re.compile(
    r"\s+(?:and|then)\s+(?=(?:ask|book|buy|call|cancel|check|confirm|draft|email|finish|follow|message|"
    r"order|pay|prepare|read|reply|review|schedule|send|share|submit|text|update|write)\b)",
    re.IGNORECASE,
)


def recover_explicit_facts(result: ExtractionResult, raw_text: str) -> ExtractionResult:
    """Fill only facts whose syntax is explicit enough to avoid interpretation."""
    expenses = _extract_expenses(raw_text, existing=result.expenses)
    actions = _extract_reminders(raw_text, existing=result.action_items)
    if not expenses and not actions:
        return result

    recovered = result.model_copy(deep=True)
    recovered.expenses.extend(expenses)
    recovered.action_items.extend(actions)
    logger.info(
        "Recovered {} explicit expenses and {} explicit reminders",
        len(expenses),
        len(actions),
    )
    return recovered


def _extract_expenses(raw_text: str, *, existing: list[ExtractedExpense]) -> list[ExtractedExpense]:
    recovered: list[ExtractedExpense] = []
    existing_amounts = {round(item.amount, 2) for item in existing if item.amount is not None}
    for match in _MONEY_RE.finditer(raw_text):
        amount = float(match.group("amount"))
        if round(amount, 2) in existing_amounts:
            continue
        context_start = max(0, match.start() - 220)
        context_end = min(len(raw_text), match.end() + 140)
        before = raw_text[context_start : match.start()]
        after = raw_text[match.end() : context_end]
        if not _PURCHASE_CUE_RE.search(_sentence_containing(raw_text, match.start(), match.end())):
            continue

        merchant = _nearest_merchant(before, after)
        reason = _expense_reason(before, after)
        recovered.append(
            ExtractedExpense(
                amount=amount,
                currency="USD",
                merchant_or_place=merchant,
                reason=reason,
            )
        )
        existing_amounts.add(round(amount, 2))
    return recovered


def _nearest_merchant(before: str, after: str) -> str | None:
    candidates: list[tuple[int, str]] = []
    for match in _MERCHANT_RE.finditer(before):
        candidates.append((len(before) - match.end(), match.group("merchant").strip()))
    for match in _MERCHANT_RE.finditer(after):
        candidates.append((match.start(), match.group("merchant").strip()))
    if not candidates:
        return None
    distance, merchant = min(candidates, key=lambda item: item[0])
    return merchant if distance <= 180 else None


def _expense_reason(before: str, after: str) -> str | None:
    after_match = _REASON_AFTER_AMOUNT_RE.search(after)
    if after_match:
        return after_match.group("reason").strip(" ,")
    before_match = _REASON_BEFORE_MERCHANT_RE.search(before[-160:])
    if before_match:
        return before_match.group("reason").strip(" ,")
    return None


def _extract_reminders(raw_text: str, *, existing: list[ExtractedActionItem]) -> list[ExtractedActionItem]:
    existing_descriptions = {_normalize(item.description) for item in existing}
    recovered: list[ExtractedActionItem] = []
    for match in _REMINDER_RE.finditer(raw_text):
        if not _is_direct_reminder_request(raw_text, match.start()):
            continue
        due_at = (match.group("before") or match.group("after") or "").strip() or None
        owner = match.group("owner").strip()
        if owner.casefold() in {"me", "myself"}:
            owner = "User"
        for description in _split_reminder_tasks(match.group("description")):
            normalized = _normalize(description)
            if not normalized or normalized in existing_descriptions:
                continue
            recovered.append(
                ExtractedActionItem(
                    description=description,
                    due_at=due_at,
                    owner=owner,
                )
            )
            existing_descriptions.add(normalized)
    return recovered


def _is_direct_reminder_request(text: str, match_start: int) -> bool:
    sentence_start = max(text.rfind(delimiter, 0, match_start) for delimiter in ".!?\n") + 1
    prefix = " ".join(text[sentence_start:match_start].strip(" ,:").split())
    return bool(_DIRECT_REQUEST_PREFIX_RE.fullmatch(prefix))


def _split_reminder_tasks(description: str) -> list[str]:
    return [part.strip(" ,") for part in _COORDINATED_TASK_RE.split(description) if part.strip(" ,")]


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _sentence_containing(text: str, start: int, end: int) -> str:
    left = max(text.rfind(delimiter, 0, start) for delimiter in ".!?\n") + 1
    right_candidates = [position for delimiter in ".!?\n" if (position := text.find(delimiter, end)) >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left:right]
