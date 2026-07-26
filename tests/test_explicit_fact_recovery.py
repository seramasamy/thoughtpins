from __future__ import annotations

from thoughtpins.ingestion.explicit_facts import recover_explicit_facts
from thoughtpins.llm import ExtractedActionItem, ExtractedExpense, ExtractionResult


def test_recovers_explicit_expenses_and_merchants() -> None:
    result = recover_explicit_facts(
        ExtractionResult(),
        (
            "Quick note from Green Bar. I spent $12 on the drink. "
            "Later I spent $7.20 at Blue Bottle on a cortado. "
            "I picked up groceries at FreshMart for $34.18."
        ),
    )

    expenses = {round(item.amount or 0, 2): item for item in result.expenses}
    assert expenses[12.0].merchant_or_place == "Green Bar"
    assert expenses[12.0].reason == "the drink"
    assert expenses[7.2].merchant_or_place == "Blue Bottle"
    assert expenses[7.2].reason == "a cortado"
    assert expenses[34.18].merchant_or_place == "FreshMart"
    assert expenses[34.18].reason == "groceries"


def test_ignores_money_without_purchase_language() -> None:
    result = recover_explicit_facts(
        ExtractionResult(),
        "The portfolio moved by $500 and the budget target remains $2000.",
    )

    assert result.expenses == []


def test_purchase_word_in_another_sentence_does_not_create_expense() -> None:
    result = recover_explicit_facts(
        ExtractionResult(),
        "I spent two hours reviewing the plan. The portfolio moved by $500.",
    )

    assert result.expenses == []


def test_recovers_both_explicit_reminder_word_orders() -> None:
    result = recover_explicit_facts(
        ExtractionResult(),
        ("Tomorrow at 3pm, remind me to text Maya the demo notes. Remind me next week to book the dentist."),
    )

    actions = {item.description: item.due_at for item in result.action_items}
    assert actions["text Maya the demo notes"] == "Tomorrow at 3pm"
    assert actions["book the dentist"] == "next week"


def test_recovers_named_owner_and_splits_coordinated_tasks() -> None:
    result = recover_explicit_facts(
        ExtractionResult(),
        "Tomorrow at 10am, remind Dana to draft the checklist and send Priya the notes.",
    )

    assert [(item.description, item.due_at, item.owner) for item in result.action_items] == [
        ("draft the checklist", "Tomorrow at 10am", "Dana"),
        ("send Priya the notes", "Tomorrow at 10am", "Dana"),
    ]


def test_does_not_recover_reminder_from_reported_speech_or_negation() -> None:
    result = recover_explicit_facts(
        ExtractionResult(),
        "Dana asked whether I could remind her to call Maya. Don't remind me to send the draft.",
    )

    assert result.action_items == []


def test_does_not_duplicate_existing_expense_or_reminder() -> None:
    initial = ExtractionResult(
        expenses=[ExtractedExpense(amount=8, merchant_or_place="Atlas Cafe")],
        action_items=[ExtractedActionItem(description="send Maya the draft")],
    )

    result = recover_explicit_facts(
        initial,
        "I spent $8 at Atlas Cafe. Tomorrow remind me to send Maya the draft.",
    )

    assert result is initial
    assert len(result.expenses) == 1
    assert len(result.action_items) == 1
