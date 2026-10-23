import uuid

import numpy as np

from docmind.ai.extractive import NOT_FOUND, answer_units, extractive_answer
from tests.unit.helpers import source

HANDBOOK = uuid.uuid4()


def test_answers_with_the_best_sentence_and_cites_it() -> None:
    sources = [
        source(
            "Time off\n\nEvery full-time employee receives 24 working days of paid annual leave per year. "
            "Sick leave is 10 days.",
            n=1,
            title="Employee Handbook",
            location="Page 2",
        ),
        source("Travel\n\nMeals are covered up to $75 per day.", n=2, title="Employee Handbook"),
    ]
    answer = extractive_answer("How many days of annual leave do employees get?", sources)
    assert answer.confident
    assert answer.text == "Every full-time employee receives 24 working days of paid annual leave per year. [1]"


def test_says_so_when_the_documents_do_not_cover_the_question() -> None:
    sources = [source("Our offices are in Austin, Berlin and Pune.", n=1)]
    answer = extractive_answer("What is the capital of France?", sources)
    assert not answer.confident
    assert answer.text.startswith(NOT_FOUND)
    assert "[1]" in answer.text


def test_list_items_travel_with_their_siblings() -> None:
    deck = (
        "Key risks\n\n\N{BULLET} LiDAR supply: a single supplier provides every sensor\n\n"
        "\N{BULLET} Customer concentration: the top five customers are 38 percent of revenue\n\n"
        "\N{BULLET} Regulation: new safety rules need legal review"
    )
    answer = extractive_answer("What are the key risks?", [source(deck, n=1, title="Board deck")])
    assert answer.text.count("\n- ") == 2 and answer.text.startswith("- LiDAR supply")


def test_a_matching_question_heading_returns_its_whole_section() -> None:
    faq = (
        "How do I reset an Atlas robot?\n\nPress and hold the power button for 10 seconds. "
        "Wait 30 seconds, then press it once. The robot restarts within two minutes."
    )
    answer = extractive_answer("How do I reset an Atlas robot?", [source(faq, n=1, title="Support FAQ")])
    assert "Press and hold the power button for 10 seconds." in answer.text
    assert "The robot restarts within two minutes." in answer.text


def test_superlatives_compare_a_numeric_column() -> None:
    table = (
        "Site: Reno; Picks per hour: 412; Status: Completed\n\n"
        "Site: Rotterdam; Picks per hour: 455; Status: Completed\n\n"
        "Site: Pune; Picks per hour: 361; Status: Completed"
    )
    sources = [source(table, n=1, title="pilot results")]
    best = extractive_answer("Which site had the best pick rate?", sources)
    worst = extractive_answer("Which site had the lowest picks per hour?", sources)
    assert best.text.startswith("Rotterdam has the highest picks per hour: 455 [1].")
    assert worst.text.startswith("Pune has the lowest picks per hour: 361 [1].")


def test_naming_a_document_targets_it() -> None:
    notes = source(
        "NEW\n\n- Multi-floor mapping across six floors.\n\n- Zone speed limits for packing areas.",
        n=2,
        title="Release notes 4.2",
        heading="NEW",
    )
    deck = source("The plan adds 96 new hires and 14 new customers.", n=1, title="Board deck")
    answer = extractive_answer("What is new in release 4.2?", [deck, notes])
    assert "[1]" not in answer.text
    assert "Multi-floor mapping" in answer.text


def test_meaning_breaks_ties_between_lexically_equal_units() -> None:
    sources = [source("Uptime is reported monthly. Availability is committed at 99.9 percent.", n=1)]
    units = answer_units(sources)
    similarities = np.array([0.1, 0.9], dtype=np.float32)
    answer = extractive_answer("What availability is committed?", sources, units=units, similarities=similarities)
    assert answer.text.startswith("Availability is committed at 99.9 percent.")


def test_units_skip_headings_and_column_summaries() -> None:
    units = answer_units([source("Columns: Site, Region.\n\nKey risks\n\nA real sentence about risks here.", n=1)])
    assert [u.text for u in units] == ["A real sentence about risks here."]
    assert units[0].heading == "Key risks"
