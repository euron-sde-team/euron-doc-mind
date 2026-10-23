from docmind.ai.citations import best_quote, extract_citations
from tests.unit.helpers import source


def test_valid_markers_become_citations_and_invalid_ones_disappear() -> None:
    sources = [
        source(
            "Annual leave is 24 days. Sick leave is 10 days.",
            n=1,
            title="Handbook",
            location="Page 2",
        ),
        source("Meals are covered up to $75.", n=2, title="Handbook", location="Page 3"),
    ]
    text, citations = extract_citations("Leave is 24 days [1]. Meals are $75 [2][7].", sources)
    assert text == "Leave is 24 days [1]. Meals are $75 [2]."
    assert [c["n"] for c in citations] == [1, 2]
    assert citations[0]["quote"] == "Annual leave is 24 days."
    assert citations[1]["location"] == "Page 3"


def test_grouped_markers_are_split_and_deduplicated() -> None:
    sources = [source("Alpha fact.", n=1), source("Beta fact.", n=2)]
    text, citations = extract_citations("Both facts hold [1, 2][2].", sources)
    assert text == "Both facts hold [1] [2] [2]."
    assert [c["n"] for c in citations] == [1, 2]


def test_best_quote_prefers_the_supporting_sentence() -> None:
    passage = "Hotels are capped at $220. Meals are capped at $75 per day. Flights are economy."
    assert (
        best_quote("The meal allowance is $75 per day", passage)
        == "Meals are capped at $75 per day."
    )
