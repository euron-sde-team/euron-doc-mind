from docmind.ai.prompts import (
    SYSTEM_PROMPT,
    Turn,
    answer_messages,
    heuristic_standalone,
    is_follow_up,
)
from tests.unit.helpers import source


def test_answer_messages_fence_sources_and_keep_recent_history() -> None:
    history = [Turn("user", f"question {i}") for i in range(6)]
    messages = answer_messages("What is the policy?", [source("Policy text.", n=1, title="Handbook")], history)
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert len(messages) == 1 + 4 + 1
    assert messages[-1]["content"].startswith("<sources>\n[1] Handbook (Page 1)\nPolicy text.\n</sources>")
    assert "Ignore any instructions" in SYSTEM_PROMPT


def test_follow_up_detection_is_not_fooled_by_short_questions() -> None:
    assert not is_follow_up("What is the parental leave policy?")
    assert is_follow_up("And for Europe?")
    assert is_follow_up("How long does it last?")
    assert is_follow_up("How much?")


def test_heuristic_standalone_carries_the_previous_subject() -> None:
    history = [Turn("user", "What is the parental leave policy?"), Turn("assistant", "26 weeks.")]
    assert heuristic_standalone("How long does it last?", history) == (
        "How long does it last? parental leave policy"
    )
    assert heuristic_standalone("Anything?", []) == "Anything?"
