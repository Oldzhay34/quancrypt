"""The templates (P4.5): the five clarification questions are the core-service V2 seed word for word, every intent has a
Turkish and an English example, and the keyword fallback maps each example to its intent."""

from __future__ import annotations

import re
from pathlib import Path

from src.prompts.templates import (
    CLARIFICATION_QUESTIONS,
    INTENT_EXAMPLES,
    INTENTS,
    match_intent,
)

SEED = (
    Path(__file__).resolve().parents[4]
    / "services"
    / "core-service"
    / "src"
    / "main"
    / "resources"
    / "db"
    / "migration"
    / "V2__lookup_data.sql"
)


def _seed_texts() -> dict[str, tuple[str, str]]:
    # INSERT INTO clarification_question (code, text_tr, text_en, ...) VALUES ('CODE', 'tr', 'en', 'kind', n);
    pattern = re.compile(
        r"INSERT INTO clarification_question \(code, text_tr, text_en, answer_kind, sort_order\) VALUES "
        r"\('([A-Z_]+)', '((?:[^']|'')*)', '((?:[^']|'')*)', '[A-Z_]+', \d+\);"
    )
    texts = {}
    for code, tr, en in pattern.findall(SEED.read_text("utf-8")):
        texts[code] = (tr.replace("''", "'"), en.replace("''", "'"))
    return texts


def test_the_clarification_questions_match_the_core_seed_word_for_word() -> None:
    seed = _seed_texts()
    assert set(CLARIFICATION_QUESTIONS) == set(seed)
    for code, (tr, en) in CLARIFICATION_QUESTIONS.items():
        assert (tr, en) == seed[code], code


def test_the_five_questions_are_in_the_core_order() -> None:
    assert list(CLARIFICATION_QUESTIONS) == [
        "TLS_TERMINATION",
        "JDK_UPGRADE_POSSIBLE",
        "HYBRID_INCAPABLE_PARTNERS",
        "COMPLIANCE_REQUIREMENT",
        "DEVICE_HARDWARE_OPENSSL",
    ]


def test_every_intent_but_unknown_has_a_turkish_and_an_english_example() -> None:
    # The examples are listed as (Turkish, English) pairs per intent: even index tr, odd index en.
    languages: dict[str, set[str]] = {intent: set() for intent in INTENTS if intent != "unknown"}
    for index, (_text, intent) in enumerate(INTENT_EXAMPLES):
        languages[intent].add("tr" if index % 2 == 0 else "en")
    assert all(seen == {"tr", "en"} for seen in languages.values()), languages


def test_the_keyword_fallback_maps_each_example_to_its_intent() -> None:
    for text, intent in INTENT_EXAMPLES:
        assert match_intent(text) == intent, text


def test_an_unrelated_question_is_unknown() -> None:
    assert match_intent("Tell me a joke about cats.") == "unknown"


def test_the_clarification_options_match_the_core_seed() -> None:
    from src.prompts.templates import CLARIFICATION_OPTIONS

    pattern = re.compile(
        r"INSERT INTO clarification_option \(question_code, option_code, text_tr, text_en, sort_order\) VALUES "
        r"\('([A-Z_]+)', '([A-Z_]+)', '([A-Z_]+)', '([A-Z_]+)', (\d+)\);"
    )
    seed: dict[str, list[tuple[int, str]]] = {code: [] for code in CLARIFICATION_QUESTIONS}
    for question, option, text_tr, text_en, order in pattern.findall(SEED.read_text("utf-8")):
        assert text_tr == option and text_en == option  # the seed's texts are the codes themselves
        seed[question].append((int(order), option))
    assert {code: tuple(o for _, o in sorted(items)) for code, items in seed.items()} == CLARIFICATION_OPTIONS


def test_where_questions_are_inventory_questions() -> None:
    assert match_intent("Servisler arasında RSA nerede?") == "inventory"
    assert match_intent("Where is RSA used between services?") == "inventory"
