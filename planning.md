# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock `listings.json` dataset for items that match the user's free-text description, then filters by size and price, returning matches sorted by relevance (best match first).

**Input parameters:**
- `description` (str): Free-text keywords describing what the user is looking for (e.g., `"vintage graphic tee"`). Used to score each listing by keyword overlap with its `title`, `description`, and `style_tags`.
- `size` (str | None): A size string to filter by (e.g., `"M"`). Matching is case-insensitive and uses substring matching (e.g., `"M"` matches a listing with `size: "S/M"`). `None` skips size filtering entirely.
- `max_price` (float | None): The highest price the user is willing to pay (inclusive). Listings priced above this are excluded. `None` skips price filtering entirely.

**What it returns:**
A list of listing dicts, each containing: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Only listings that pass the size/price filters AND have at least one keyword match with `description` are included. The list is sorted highest-score-first. If nothing matches, returns `[]`.

**What happens if it fails or returns nothing:**
`search_listings` never raises — it returns `[]`. The planning loop checks `len(session["search_results"]) == 0`. If true, it sets `session["error"]` to a specific message (naming the description/size/price the user searched for and suggesting a concrete adjustment, e.g. "try a higher price limit or drop the size filter") and returns the session immediately. `suggest_outfit` and `create_fit_card` are NOT called in this case.

---

### Tool 2: suggest_outfit

**What it does:**
Given the listing the user is considering and their wardrobe, calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 outfit pairings using specific wardrobe pieces, or general styling advice if the wardrobe is empty.

**Input parameters:**
- `new_item` (dict): The selected listing dict (from `search_results[0]`) — the item the user is considering buying.
- `wardrobe` (dict): A dict with key `"items"` mapping to a list of wardrobe item dicts (`id`, `name`, `category`, `colors`, `style_tags`, `notes`). `wardrobe["items"]` may be `[]`.

**What it returns:**
A non-empty string. If `wardrobe["items"]` is non-empty, the string references specific wardrobe items by name (e.g., "your baggy straight-leg jeans and chunky white sneakers") and describes how to style the new item with them. If `wardrobe["items"]` is empty, the string contains general styling advice for the new item (what it pairs well with, what vibe it suits) without referencing nonexistent wardrobe items.

**What happens if it fails or returns nothing:**
An empty wardrobe is NOT treated as a failure — it's an expected input that produces general advice instead of personalized advice (see above). If the Groq API call itself raises (e.g., missing/invalid `GROQ_API_KEY`, network error), the function catches the exception and returns a fallback string such as `"Couldn't generate styling suggestions right now, but here's the item: <new_item['title']>."` so the planning loop always has a string to pass to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Given the outfit suggestion and the selected listing, calls the Groq LLM to generate a short, casual social-media caption (like a real thrift OOTD post) for the item.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): The selected listing dict — used for the item's title, price, and platform.

**What it returns:**
A 2–4 sentence string suitable as an Instagram/TikTok caption. It mentions the item's title, price, and platform once each, and reflects the vibe described in `outfit`. Temperature is set high enough that repeated calls with the same inputs produce different wording.

**What happens if it fails or returns nothing:**
If `outfit` is empty, `None`, or whitespace-only, `create_fit_card` does NOT call the LLM. It returns a descriptive string instead, e.g. `"Couldn't generate a fit card for <new_item['title']> — no outfit suggestion was available."` This is a string, never a raised exception, so the planning loop can safely store it in `session["fit_card"]` and `session["error"]` stays `None` (the user still sees the item they found, just without a caption).

---

### Additional Tools (if any)

None for the core implementation. (If a stretch feature adds a tool — e.g., a price-comparison or wardrobe-gap tool — copy the block above and fill it in here, and update the Architecture diagram below.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop (`run_agent` in `agent.py`) runs once per user query, in a fixed sequence with exactly one conditional branch:

1. **Initialize**: `session = _new_session(query, wardrobe)`.
2. **Parse**: Extract `description`, `size`, and `max_price` from the raw `query` string (e.g., regex for a `$` amount → `max_price`, a standalone size token like "size M" → `size`, and the remaining text → `description`). Store the result as `session["parsed"] = {"description": ..., "size": ..., "max_price": ...}`.
3. **Search**: Call `search_listings(**session["parsed"])`. Store the returned list in `session["search_results"]`.
4. **Branch on results**:
   - If `session["search_results"] == []`: set `session["error"]` to a specific, actionable message (see Error Handling table) and **return `session` immediately**. `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` all remain `None`. `suggest_outfit` and `create_fit_card` are never called.
   - Otherwise: set `session["selected_item"] = session["search_results"][0]` and continue to step 5.
5. **Suggest outfit**: Call `suggest_outfit(session["selected_item"], session["wardrobe"])`. Store the returned string in `session["outfit_suggestion"]`.
6. **Create fit card**: Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. Store the returned string in `session["fit_card"]`.
7. **Return** `session`.

The agent "knows it's done" after step 7 — there is no further looping or re-querying within a single `run_agent` call. The only point where behavior diverges based on tool output is step 4 (empty vs. non-empty search results); once results exist, steps 5 and 6 always execute.

---

## State Management

**How does information from one tool get passed to the next?**

A single session dict (created once by `_new_session(query, wardrobe)` at the start of `run_agent`) is threaded through the entire interaction. Each step reads from and writes to specific keys:

- `session["query"]` — the original raw user string. Set once at init, never modified.
- `session["parsed"]` — `{"description": str, "size": str|None, "max_price": float|None}`, written by step 2, read by step 3 (unpacked as kwargs into `search_listings`).
- `session["search_results"]` — the list returned by `search_listings`, written by step 3, read by step 4.
- `session["selected_item"]` — `search_results[0]`, written by step 4 (non-empty branch), read by step 5 (as `new_item`) and step 6 (as `new_item`).
- `session["wardrobe"]` — set once at init from the `wardrobe` argument, read by step 5.
- `session["outfit_suggestion"]` — the string returned by `suggest_outfit`, written by step 5, read by step 6 (as `outfit`).
- `session["fit_card"]` — the string returned by `create_fit_card`, written by step 6. This is the final user-facing result.
- `session["error"]` — `None` unless step 4's empty-results branch fires, in which case it's set to a specific message and the session is returned early.

Tools themselves remain pure functions — they receive plain arguments (`new_item`, `wardrobe`, `outfit`, etc.) and return plain values. Only the planning loop touches the `session` dict; this keeps each tool independently testable (per Milestone 3) without needing to construct a full session.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (`search_results == []`) | `session["error"]` is set to a message like: `"I couldn't find any listings matching 'vintage graphic tee' under $5 (size XXS). Try raising your price limit, removing the size filter, or using broader keywords like 'tee' instead of 'graphic tee'."` The loop returns immediately — `selected_item`, `outfit_suggestion`, and `fit_card` stay `None`. The user sees only this message and no other panels populate. |
| suggest_outfit | Wardrobe is empty (`wardrobe["items"] == []`) | Not an exception — `suggest_outfit` returns general styling advice, e.g. `"This faded band tee has an easy 90s-grunge vibe — it'd pair well with straight-leg or wide-leg jeans and chunky sneakers or boots, plus a denim jacket if it's cool out."` The loop proceeds normally to `create_fit_card` with this string as `outfit`. |
| create_fit_card | Outfit input is missing or incomplete (`outfit` is `""`, whitespace, or `None`) | `create_fit_card` returns `"Couldn't generate a fit card for Graphic Tee — 2003 Tour Bootleg Style — no outfit suggestion was available to build a caption from."` without calling the LLM. `session["fit_card"]` is set to this string; `session["error"]` stays `None` since the search and item info are still valid and shown to the user — only the caption panel shows this fallback text. |

---

## Architecture

```
User query
    │
    ▼
run_agent()  [Planning Loop]
    │
    ├─► Step 2: Parse query
    │       │
    │       ▼
    │   session["parsed"] = {description, size, max_price}
    │
    ├─► Step 3: search_listings(description, size, max_price)
    │       │
    │       ├─ search_results = []
    │       │       │
    │       │       ▼
    │       │   session["error"] = "No listings found for '<description>'... try <suggestion>"
    │       │       │
    │       │       └──► RETURN session   (selected_item, outfit_suggestion, fit_card = None)
    │       │
    │       └─ search_results = [item, ...]
    │               │
    │               ▼
    │           session["search_results"] = [item, ...]
    │           session["selected_item"]  = search_results[0]
    │
    ├─► Step 5: suggest_outfit(selected_item, wardrobe)
    │       │
    │       ▼
    │   session["outfit_suggestion"] = "<styling suggestion text>"
    │
    └─► Step 6: create_fit_card(outfit_suggestion, selected_item)
            │
            ▼
        session["fit_card"] = "<caption text>"
            │
            ▼
        RETURN session   (error = None)
            │
            ▼
        App displays: item details | outfit_suggestion | fit_card
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

For `search_listings`, I'll give Claude the Tool 1 block above (inputs, return value, failure mode) plus the existing docstring/TODO comments from `tools.py`, and ask it to implement the function using `load_listings()`. Before running it, I'll verify the generated code: (1) filters out listings above `max_price` when provided, (2) does case-insensitive substring matching on `size` when provided, (3) scores remaining listings by keyword overlap between `description` and the listing's `title`/`description`/`style_tags`, (4) drops zero-score listings, (5) sorts by score descending, and (6) returns `[]` (not an exception) when nothing matches. Then I'll test it with three queries: a normal query that should return matches, a query designed to return nothing (e.g., "designer ballgown" size "XXS" under $5), and a query using only `max_price` with `size=None`.

For `suggest_outfit`, I'll give Claude the Tool 2 block above plus the `tools.py` docstring, and ask it to implement the function using the Groq client already set up in `_get_groq_client()`. Before running it, I'll verify: (1) it checks `wardrobe["items"]` for emptiness and builds a different prompt for each case, (2) it always returns a non-empty string, and (3) a Groq API failure is caught and produces a fallback string rather than crashing. I'll test it twice — once with `get_example_wardrobe()` and once with `get_empty_wardrobe()` — and confirm the empty-wardrobe response gives general advice without inventing wardrobe items.

For `create_fit_card`, I'll give Claude the Tool 3 block above plus the docstring, and ask it to implement the function. Before running it, I'll verify: (1) it guards against an empty/whitespace `outfit` and returns a descriptive string without calling the LLM in that case, (2) the prompt mentions the item's title, price, and platform, and (3) temperature is set high enough that two runs with the same inputs produce different captions. I'll run it 3 times on the same inputs and confirm the captions vary, then run it once with `outfit=""` and confirm it returns the fallback string, not an exception.

**Milestone 4 — Planning loop and state management:**

I'll give Claude this entire planning.md's Planning Loop, State Management, and Architecture sections (including the diagram above), plus the numbered TODO comments already in `agent.py`, and ask it to implement `run_agent()`. Before running it, I'll verify the generated code: (1) calls `_new_session()` exactly once at the start, (2) writes `session["parsed"]` before calling `search_listings`, (3) checks `len(session["search_results"]) == 0` and — if true — sets `session["error"]` and returns early WITHOUT calling `suggest_outfit` or `create_fit_card`, (4) sets `session["selected_item"] = session["search_results"][0]` only on the non-empty branch, and (5) passes `selected_item`/`wardrobe`/`outfit_suggestion` into the later tool calls exactly as described in State Management. I'll verify by running `python agent.py` and confirming both the happy-path block and the no-results block in `__main__` produce the expected `session["error"]` values (`None` vs. a specific message).

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

FitFindr helps a user find a secondhand item that matches their description, size, and budget, suggests how to style it using items already in their wardrobe, and generates a short social-media-style caption for the resulting outfit. `search_listings` runs first, triggered by the user's search terms; if it returns at least one match, the top result and the user's wardrobe trigger `suggest_outfit`, whose output then triggers `create_fit_card`. If `search_listings` returns no results, the agent stops immediately, tells the user what to adjust (e.g., a higher price limit or different size), and never calls `suggest_outfit` or `create_fit_card` with empty input.

**Step 1:**
The planning loop parses the query into `session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}` and calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. Against `listings.json`, the top-scoring match is `lst_002` — "Y2K Baby Tee — Butterfly Print" ($18, depop, excellent condition, size S/M, colors white/pink/purple, style_tags include "y2k", "vintage", "graphic tee", "cottagecore") — along with several other listings under $30 with overlapping keywords. `search_results` is non-empty, so `session["search_results"]` is set to this list.

**Step 2:**
Since `search_results` is non-empty, `session["selected_item"] = search_results[0]` (the $18 Y2K baby tee from depop). The loop calls `suggest_outfit(selected_item, wardrobe)` with `wardrobe = get_example_wardrobe()`. The LLM returns a string referencing real wardrobe pieces by name — e.g., pairing the baby tee with "Baggy straight-leg jeans, dark wash" and "Chunky white sneakers" for a nostalgic, playful look, with a layering option using the "Oversized grey crewneck sweatshirt" and "black combat boots" for cooler weather. `session["outfit_suggestion"]` is set to this string.

**Step 3:**
The loop calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM generates a casual caption mentioning the item ("Y2K Baby Tee — Butterfly Print"), its $18 price, depop, and the nostalgic/playful vibe from the outfit suggestion (e.g., "Just scored this adorable Y2K Baby Tee — Butterfly Print on Depop for $18 and I'm obsessed! I paired it with my fave baggy jeans and chunky whites for a super nostalgic and playful vibe 🦋"). `session["fit_card"]` is set to this string. `session["error"]` remains `None`.

**Final output to user:**
The Gradio app's three panels populate: (1) the found item — "Y2K Baby Tee — Butterfly Print, $18.00, depop, excellent condition, Size S/M, colors white/pink/purple"; (2) the outfit suggestion text pairing it with the user's baggy jeans and chunky white sneakers, with an optional cooler-weather layering combo; (3) the fit card caption — a short, casual post-style caption mentioning the item, price, platform, and vibe, ready to share.