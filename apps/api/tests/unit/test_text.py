from docmind.core.text import content_terms, normalize, sentence_spans, split_sentences, truncate


def test_normalize_collapses_spacing_and_blank_lines() -> None:
    raw = "Line  one\N{NO-BREAK SPACE}here\r\n\r\n\r\n\r\nLine\ttwo\N{SOFT HYPHEN}"
    assert normalize(raw) == "Line one here\n\nLine two"


def test_sentences_respect_abbreviations_and_decimals() -> None:
    text = "Revenue grew 32 percent, e.g. in hardware. The margin was 61.5 percent. Dr. Lee agreed."
    assert split_sentences(text) == [
        "Revenue grew 32 percent, e.g. in hardware.",
        "The margin was 61.5 percent.",
        "Dr. Lee agreed.",
    ]


def test_sentence_spans_slice_the_original_text() -> None:
    text = "First one. Second one! Third?"
    spans = sentence_spans(text)
    assert [text[s:e] for s, e in spans] == ["First one.", "Second one!", "Third?"]


def test_stemming_is_consistent_between_questions_and_passages() -> None:
    assert set(content_terms("hiring hires hired hire")) == {"hir"}
    assert content_terms("policies") == content_terms("policy")
    assert content_terms("approved approve") == ["approv", "approv"]


def test_content_terms_drop_stopwords_and_keep_numbers() -> None:
    assert content_terms("What is the FY2027 budget for 4.2?") == ["fy2027", "budget", "4.2"]


def test_truncate_cuts_on_a_word_boundary() -> None:
    assert truncate("alpha beta gamma delta", 12) == "alpha beta..."
    assert truncate("short", 12) == "short"
