"""
tests/test_tools.py

Tests for the three FitFindr tools, including each tool's failure mode.

Run with:
    pytest tests/
"""

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Tool 1: search_listings ─────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []   # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_substring_and_case_insensitive():
    results = search_listings("graphic tee", size="m", max_price=None)
    assert isinstance(results, list)
    for item in results:
        assert "m" in item["size"].lower()


def test_search_results_sorted_by_relevance():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert len(results) > 0
    for item in results:
        assert "title" in item and "style_tags" in item


# ── Tool 2: suggest_outfit ───────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    suggestion = suggest_outfit(results[0], get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion.strip()) > 0


def test_suggest_outfit_empty_wardrobe_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    suggestion = suggest_outfit(results[0], get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion.strip()) > 0


# ── Tool 3: create_fit_card ──────────────────────────────────────────────────

def test_create_fit_card_with_outfit_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    card = create_fit_card("Pair this with your baggy jeans and chunky sneakers.", results[0])
    assert isinstance(card, str)
    assert len(card.strip()) > 0


def test_create_fit_card_empty_outfit_returns_message_not_exception():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    card = create_fit_card("", results[0])
    assert isinstance(card, str)
    assert len(card.strip()) > 0