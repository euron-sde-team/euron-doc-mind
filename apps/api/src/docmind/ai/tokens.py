"""Token counting for context budgets and the savings meter.

Uses tiktoken's o200k_base encoding (a close proxy for current hosted models). If the
encoding cannot be loaded (an air-gapped host without the cached file), it falls back to
the four-characters-per-token rule and says so in the log once.
"""

from __future__ import annotations

from typing import Any

from docmind.core.logging import get_logger

log = get_logger("docmind.tokens")


class TokenCounter:
    def __init__(self, mode: str = "tiktoken") -> None:
        self._encoding: Any = None
        self.name = "heuristic"
        if mode == "tiktoken":
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding("o200k_base")
                self.name = "o200k_base"
            except Exception as exc:
                log.warning("tokenizer_fallback", fallback="heuristic", error=str(exc))

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode_ordinary(text))
        return max(1, (len(text) + 3) // 4)

    def truncate(self, text: str, max_tokens: int) -> str:
        if self.count(text) <= max_tokens:
            return text
        if self._encoding is not None:
            decoded: str = self._encoding.decode(self._encoding.encode_ordinary(text)[:max_tokens])
            return decoded
        return text[: max_tokens * 4]
