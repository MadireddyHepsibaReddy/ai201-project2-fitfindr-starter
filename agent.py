"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parsing ────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract a description, optional size, and optional max_price from a
    natural-language query using regex.

    Documented in planning.md (Planning Loop, Step 2): regex-based parsing
    was chosen over an LLM call here to keep search_listings fast and
    deterministic — the listings dataset and size formats are simple enough
    that pattern matching covers the expected query shapes.

    Returns:
        {"description": str, "size": str | None, "max_price": float | None}
    """
    text = query

    # max_price: "$30", "under $30", "below $30", "for $30", etc.
    max_price = None
    price_match = re.search(r"\$(\d+(?:\.\d+)?)", text)
    if price_match:
        max_price = float(price_match.group(1))
        text = re.sub(
            r"\b(under|below|less than|for|around)?\s*\$\d+(?:\.\d+)?",
            "",
            text,
            flags=re.IGNORECASE,
        )

    # size: "size M", "size W30", "size S/M", etc.
    size = None
    size_match = re.search(r"\bsize\s+([A-Za-z0-9/\-]+)", text, flags=re.IGNORECASE)
    if size_match:
        size = size_match.group(1)
        text = re.sub(r"\bsize\s+[A-Za-z0-9/\-]+", "", text, flags=re.IGNORECASE)

    # strip common filler phrases that aren't useful as search keywords
    filler_phrases = [
        r"\bi'?m looking for\b",
        r"\bi am looking for\b",
        r"\blooking for\b",
        r"\ba\b",
        r"\ban\b",
        r"\bi mostly wear.*$",
        r"\bwhat'?s out there.*$",
        r"\bhow would i style (it|this).*$",
    ]
    for phrase in filler_phrases:
        text = re.sub(phrase, "", text, flags=re.IGNORECASE)

    # clean up punctuation and extra whitespace
    text = re.sub(r"[.,!?]", "", text)
    description = re.sub(r"\s+", " ", text).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: initialize session
    session = _new_session(query, wardrobe)

    # Step 2: parse query -> description / size / max_price
    session["parsed"] = _parse_query(query)

    # Step 3: search
    session["search_results"] = search_listings(
        description=session["parsed"]["description"],
        size=session["parsed"]["size"],
        max_price=session["parsed"]["max_price"],
    )

    # Step 3 (branch): no results -> set error and return early
    if not session["search_results"]:
        parsed = session["parsed"]
        constraints = []
        if parsed["size"]:
            constraints.append(f"size {parsed['size']}")
        if parsed["max_price"] is not None:
            constraints.append(f"under ${parsed['max_price']:g}")
        constraint_str = f" ({', '.join(constraints)})" if constraints else ""

        description = parsed["description"] or "that"
        session["error"] = (
            f"I couldn't find any listings matching '{description}'{constraint_str}. "
            "Try raising your price limit, removing the size filter, or using "
            "broader keywords (e.g., 'tee' instead of 'graphic tee')."
        )
        return session

    # Step 4: select the top result
    session["selected_item"] = session["search_results"][0]

    # Step 5: suggest an outfit
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: create the fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: return the completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")