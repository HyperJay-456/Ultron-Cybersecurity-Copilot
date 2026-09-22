"""Regression tests for tokenizer-aware token budgeting (Finding 14 remediation)."""

import pytest
from src.retrieval.budget import (
    BaseTokenizer,
    CalibratedHeuristicTokenizer,
    FastTokenizerAdapter,
    OllamaRemoteTokenizer,
    TokenBudgetController,
)


class DummyExactTokenizer(BaseTokenizer):
    """Deterministic exact test tokenizer counting whitespace-split tokens."""

    @property
    def is_exact(self) -> bool:
        return True

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(text.split())


def test_calibrated_heuristic_tokenizer_json_code_density():
    """Verify that JSON and code punctuation receive calibrated token density adjustments."""
    tokenizer = CalibratedHeuristicTokenizer(base_chars_per_token=3.5, safety_margin=1.0)

    # 101 characters of English prose
    prose = "The security analyst reviewed the application authorization logic and found an unprotected endpoint!."
    # 101 characters of dense JSON
    json_text = '{"auth":false,"headers":{"x-api-key":"abc","role":"admin"},"endpoints":["/a","/b","/c"],"status":200}'

    assert len(prose) == len(json_text)

    prose_tokens = tokenizer.count_tokens(prose)
    json_tokens = tokenizer.count_tokens(json_text)

    # JSON with high punctuation density must yield significantly higher token count
    assert json_tokens > prose_tokens
    assert tokenizer.is_exact is False


def test_calibrated_heuristic_tokenizer_unicode_overhead():
    """Verify that multibyte Unicode sequences receive appropriate token overhead weighting."""
    tokenizer = CalibratedHeuristicTokenizer(base_chars_per_token=3.5, safety_margin=1.0)

    ascii_text = "Hello world secure token"
    unicode_text = "Hello world \u3053\u3093\u306b\u3061\u306f token"  # Japanese characters

    ascii_tokens = tokenizer.count_tokens(ascii_text)
    unicode_tokens = tokenizer.count_tokens(unicode_text)

    assert unicode_tokens > ascii_tokens


def test_fast_tokenizer_adapter():
    """Verify FastTokenizerAdapter correctly extracts token counts and reports is_exact=True."""
    class MockHFTokenizer:
        def encode(self, text):
            class Encoding:
                ids = [101, 2054, 2003, 102]
            return Encoding()

    adapter = FastTokenizerAdapter(MockHFTokenizer())
    assert adapter.is_exact is True
    assert adapter.count_tokens("Arbitrary input text") == 4
    assert adapter.count_tokens("") == 0


def test_ollama_remote_tokenizer_fallback_when_offline():
    """Verify OllamaRemoteTokenizer safely falls back to calibrated heuristic when offline."""
    # Port 65530 is closed, testing graceful fallback without unhandled exception
    tokenizer = OllamaRemoteTokenizer(
        base_url="http://127.0.0.1:65530",
        model_name="qwen2.5-coder:7b",
        timeout_seconds=0.2,
    )
    tokens = tokenizer.count_tokens("SELECT * FROM users WHERE id = 1;")
    assert tokens > 0
    assert tokenizer.is_exact is True


def test_budget_controller_modes_and_caching():
    """Verify TokenBudgetController correctly tracks mode and caches frequent string counts."""
    # 1. Exact mode
    exact_tok = DummyExactTokenizer()
    controller_exact = TokenBudgetController(tokenizer=exact_tok)
    assert controller_exact.is_exact is True
    assert controller_exact.token_count_mode == "EXACT_TOKENIZER"

    # Count tokens
    assert controller_exact.count_tokens("one two three four") == 4
    # Cache hit
    assert controller_exact.count_tokens("one two three four") == 4

    # 2. Heuristic mode
    controller_heuristic = TokenBudgetController()
    assert controller_heuristic.is_exact is False
    assert controller_heuristic.token_count_mode == "CALIBRATED_HEURISTIC"


def test_budget_controller_cropping_with_exact_tokenizer():
    """Verify deterministic cropping with an exact tokenizer."""
    exact_tok = DummyExactTokenizer()
    controller = TokenBudgetController(tokenizer=exact_tok)

    chunks = [
        {"statement": "word " * 10},  # 10 tokens
        {"statement": "word " * 20},  # 20 tokens
        {"statement": "word " * 30},  # 30 tokens
    ]

    # Budget 35 tokens -> chunk 1 (10) + chunk 2 (20) = 30 <= 35; chunk 3 (30) doesn't fit
    cropped = controller.crop_chunks_to_budget(chunks, token_budget=35)
    assert len(cropped) == 2
    assert cropped[0]["statement"] == "word " * 10
    assert cropped[1]["statement"] == "word " * 20
