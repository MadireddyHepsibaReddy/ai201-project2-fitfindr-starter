"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # Step 2: filter by max_price and size (if provided)
    filtered = []
    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and size.lower() not in listing["size"].lower():
            continue
        filtered.append(listing)

    # Step 3: score each remaining listing by keyword overlap with description
    keywords = [kw for kw in description.lower().split() if kw]
    scored = []
    for listing in filtered:
        searchable_text = " ".join(
            [
                listing["title"],
                listing["description"],
                " ".join(listing["style_tags"]),
            ]
        ).lower()

        score = sum(1 for kw in keywords if kw in searchable_text)

        # Step 4: drop listings with no keyword overlap
        if score > 0:
            scored.append((score, listing))

    # Step 5: sort by score, highest first, and return the listing dicts
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    items = wardrobe.get("items", [])

    item_summary = (
        f"{new_item['title']}: {new_item['description']} "
        f"(category: {new_item['category']}, colors: {', '.join(new_item['colors'])}, "
        f"style tags: {', '.join(new_item['style_tags'])})"
    )

    if not items:
        # Step 2: empty wardrobe -> general styling advice
        prompt = (
            "A user is considering buying this secondhand item:\n"
            f"- {item_summary}\n\n"
            "They don't have any wardrobe items saved yet. Give general styling "
            "advice in 2-3 sentences: what kinds of pieces (colors, silhouettes, "
            "categories) would pair well with this item, and what overall vibe "
            "or outfit it would suit."
        )
    else:
        # Step 3: non-empty wardrobe -> suggest specific pairings by name
        wardrobe_lines = "\n".join(
            f"- {it['name']} (category: {it['category']}, colors: {', '.join(it['colors'])}, "
            f"style tags: {', '.join(it['style_tags'])}"
            + (f", notes: {it['notes']}" if it.get("notes") else "")
            + ")"
            for it in items
        )
        prompt = (
            "A user is considering buying this secondhand item:\n"
            f"- {item_summary}\n\n"
            "Here is their current wardrobe:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific "
            "pieces from this wardrobe, referring to them by name. Describe the "
            "overall vibe and any concrete styling tips (tucking, layering, "
            "rolling sleeves, etc.). Keep it to 2-4 sentences."
        )

    # Step 4: call the LLM and return its response as a string
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        result = response.choices[0].message.content.strip()
        if result:
            return result
        return (
            f"The {new_item['title']} is versatile and would work well with "
            "casual basics in neutral tones."
        )
    except Exception:
        return (
            "Couldn't generate styling suggestions right now, but here's the "
            f"item: {new_item['title']}."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Step 1: guard against an empty or whitespace-only outfit string
    if not outfit or not outfit.strip():
        return (
            f"Couldn't generate a fit card for {new_item['title']} — "
            "no outfit suggestion was available to build a caption from."
        )

    # Step 2: build the prompt
    prompt = (
        "Write a short, casual Instagram/TikTok-style caption (2-4 sentences) "
        "for an outfit-of-the-day post featuring this thrifted item:\n"
        f"- Item: {new_item['title']}\n"
        f"- Price: ${new_item['price']}\n"
        f"- Platform: {new_item['platform']}\n"
        f"- Condition: {new_item['condition']}\n\n"
        f"Outfit styling notes: {outfit}\n\n"
        "The caption should feel authentic and personal, like a real thrift "
        "find post, not a product description. Mention the item name, price, "
        "and platform naturally (once each), and capture the outfit vibe in "
        "specific terms. Casual language and an emoji or two are welcome."
    )

    # Step 3: call the LLM and return the response
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        if result:
            return result
        return (
            f"Couldn't generate a fit card for {new_item['title']} — try again "
            "in a moment."
        )
    except Exception:
        return (
            f"Couldn't generate a fit card for {new_item['title']} right now — "
            "try again in a moment."
        )