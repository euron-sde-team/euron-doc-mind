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


def test_best_quote_picks_the_matching_list_item_not_the_whole_list() -> None:
    passage = (
        "Key risks\n\n\N{BULLET} LiDAR supply: a single supplier provides all sensors\n\n"
        "\N{BULLET} Customer concentration: the top 5 customers are 38 percent of revenue"
    )

    quote = best_quote("The top 5 customers are 38 percent of revenue", passage)

    assert quote == "Customer concentration: the top 5 customers are 38 percent of revenue"


def test_each_list_item_quotes_its_own_line_of_the_source() -> None:
    passage = (
        "Key risks\n\n\N{BULLET} LiDAR supply: a single supplier provides all sensors\n\n"
        "\N{BULLET} Customer concentration: the top 5 customers are 38 percent of revenue"
    )
    answer = (
        "- LiDAR supply: a single supplier provides all sensors. [1]\n"
        "- Customer concentration: the top 5 customers are 38 percent of revenue. [1]"
    )

    _, citations = extract_citations(answer, [source(passage, n=1)])

    assert [c["quote"] for c in citations] == [
        "LiDAR supply: a single supplier provides all sensors"
    ]
