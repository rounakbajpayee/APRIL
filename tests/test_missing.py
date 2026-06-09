import pytest
from semantic_store import _tokenize, _score_match


def test_tokenize():
    tokens = _tokenize("Open the browser")
    assert "open" in tokens
    assert "browser" in tokens


def test_score_match():
    q_tokens = ["open", "browser"]
    record = {"normalized": "open browser now"}
    score = _score_match("open browser", q_tokens, record)
    assert score > 0
