# FitFindr

FitFindr is an agent that helps a user find a secondhand clothing item matching
their description, size, and budget; suggests how to style it with their
existing wardrobe; and generates a short, shareable "fit card" caption for the
result. It's built around three tools orchestrated by a planning loop in
`agent.py`, with a Gradio interface in `app.py`.

---

## Tool Inventory

### `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`

**Purpose:** Searches the mock `data/listings.json` dataset for items matching
a free-text description, optionally filtered by size and maximum price.

**Inputs:**
- `description` (str): Free-text keywords describing what the user wants (e.g. `"vintage graphic tee"`). Used to score listings by keyword overlap with their `title`, `description`, and `style_tags`.
- `size` (str | None): A size string to filter by (e.g. `"M"`). Matching is case-insensitive substring matching (`"M"` matches `"S/M"`). `None` skips size filtering.
- `max_price` (float | None): Maximum price, inclusive. `None` skips price filtering.

**Output:** A list of listing dicts (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`), filtered by size/price and containing at least one keyword match, sorted highest-relevance first. Returns `[]` if nothing matches.

---

### `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

**Purpose:** Calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 outfit pairings between a candidate listing and the user's existing wardrobe, or general styling advice if the wardrobe is empty.

**Inputs:**
- `new_item` (dict): A listing dict — the item the user is considering.
- `wardrobe` (dict): A dict with key `"items"` containing a list of wardrobe item dicts (`id`, `name`, `category`, `colors`, `style_tags`, `notes`). May be empty.

**Output:** A non-empty string. If the wardrobe has items, the string names specific wardrobe pieces by name and describes how to combine them with the new item. If the wardrobe is empty, the string gives general styling advice for the item without inventing wardrobe pieces.

---

### `create_fit_card(outfit: str, new_item: dict) -> str`

**Purpose:** Calls the Groq LLM to generate a short, casual, Instagram/TikTok-style caption for the thrifted find, based on the outfit suggestion.

**Inputs:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): The selected listing dict.

**Output:** A 2–4 sentence string mentioning the item's title, price, and platform once each, capturing the outfit's vibe. If `outfit` is empty/whitespace, returns a descriptive fallback string without calling the LLM.

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in `agent.py` runs once per user interaction, in a fixed sequence with **one conditional branch**:

1. **Initialize** a fresh session dict via `_new_session()`.
2. **Parse** the raw query string with a regex-based helper, `_parse_query()`, which extracts `description`, `size` (from a `"size X"` pattern), and `max_price` (from a `"$X"` pattern), stripping filler phrases like "I'm looking for" and "I mostly wear..." from the description. The result is stored in `session["parsed"]`.
3. **Call `search_listings`** with the parsed parameters and store the result in `session["search_results"]`.
4. **Branch:**
   - If `search_results` is empty, set `session["error"]` to a specific message (naming the description/size/price the user searched for and suggesting a concrete adjustment) and **return immediately**. `selected_item`, `outfit_suggestion`, and `fit_card` all stay `None`. `suggest_outfit` and `create_fit_card` are **never called** in this case.
   - Otherwise, set `session["selected_item"] = search_results[0]` and continue.
5. **Call `suggest_outfit`** with `selected_item` and the wardrobe; store the result in `session["outfit_suggestion"]`.
6. **Call `create_fit_card`** with `outfit_suggestion` and `selected_item`; store the result in `session["fit_card"]`.
7. **Return** the session.

The only point where the agent's behavior diverges based on tool output is step 4. Once results exist, steps 5 and 6 always run — there's no further looping, re-prompting, or re-entry within a single `run_agent` call.

---

## State Management

A single session dict, created once by `_new_session(query, wardrobe)`, is threaded through the entire interaction:

| Key | Set by | Read by |
|---|---|---|
| `query` | init | (reference only) |
| `parsed` | step 2 (`_parse_query`) | step 3 (`search_listings` kwargs) |
| `search_results` | step 3 | step 4 (branch check) |
| `selected_item` | step 4 (non-empty branch) | step 5 and step 6, as `new_item` |
| `wardrobe` | init | step 5 |
| `outfit_suggestion` | step 5 | step 6, as `outfit` |
| `fit_card` | step 6 | final output |
| `error` | step 4 (empty branch only) | caller (`app.py`) |

The three tools themselves remain pure functions — they take plain arguments and return plain values. Only `run_agent` reads from and writes to the session dict, which keeps each tool independently testable without constructing a full session (as done in `tests/test_tools.py`).

`app.py`'s `handle_query()` calls `run_agent()` once per Gradio submission and maps the resulting session dict to the three output panels: if `session["error"]` is set, it's shown alone in the first panel with the other two left empty; otherwise `selected_item` is formatted into readable text and `outfit_suggestion` / `fit_card` are passed through directly.

---

## Error Handling

| Tool | Failure mode | Agent response | Example from testing |
|---|---|---|---|
| `search_listings` | No results match the query | `session["error"]` is set to a specific message naming the search terms and suggesting a concrete fix; the loop returns early and `suggest_outfit`/`create_fit_card` are never called. | Query `"designer ballgown size XXS under $5"` → `session["error"]` = *"I couldn't find any listings matching 'designer ballgown' (size XXS, under $5). Try raising your price limit, removing the size filter, or using broader keywords (e.g., 'tee' instead of 'graphic tee')."* `session["fit_card"]` remained `None`. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"] == []`) | Not treated as an error — the tool builds a different prompt asking the LLM for general styling advice, and still returns a non-empty string. The loop proceeds normally. | With `get_empty_wardrobe()` and the Y2K Baby Tee, returned: *"This Y2K-inspired baby tee would pair perfectly with high-waisted jeans, flowy skirts, or distressed shorts for a nostalgic and playful look. To enhance its cottagecore vibe, consider pairing it with pastel-colored cardigans, floppy hats, or layered necklaces..."* — no nonexistent wardrobe items were referenced. |
| `create_fit_card` | `outfit` is empty/whitespace | Returns a descriptive fallback string without calling the LLM; `session["error"]` stays `None` since the item info is still valid. | `create_fit_card("", item)` → *"Couldn't generate a fit card for Y2K Baby Tee — Butterfly Print — no outfit suggestion was available to build a caption from."* |

---

## Spec Reflection

**How the spec helped:** Writing out the session dict structure and the step-by-step planning loop logic in `planning.md` *before* touching `agent.py` made the actual implementation almost mechanical — each TODO step in `agent.py` mapped directly to a bullet in the Planning Loop section, so there was no mid-implementation redesign of how data should flow between tools.

**Where implementation diverged from the spec:** The original `planning.md` walkthrough predicted that searching "vintage graphic tee" under $30 would surface `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style") as the top result. In practice, `lst_002` ("Y2K Baby Tee — Butterfly Print") came back first instead. Both listings matched all three keywords ("vintage", "graphic", "tee") equally under the simple presence-based scoring described in the spec, so the tie was broken by original order in `listings.json`. Rather than rewrite the scoring function to add tie-breaking weights (which the spec didn't call for), the walkthrough in `planning.md` was updated to reflect the actual top result — a reminder that "score by keyword overlap" needed a tie-breaking rule that wasn't anticipated when writing the spec.

---

## AI Usage

**Instance 1 — `search_listings` (Milestone 3):** I gave Claude the Tool 1 spec block from `planning.md` (input parameters, return shape, failure mode) along with the existing docstring/TODO steps in `tools.py`, and asked it to implement the function using `load_listings()`. Before running it, I checked that the generated code filtered on `max_price` and `size` correctly, scored remaining listings by keyword overlap, dropped zero-score listings, and returned `[]` without raising for impossible queries. I tested it with the 5 pytest cases plus a manual run against the planning.md example query — which is where I discovered the `lst_002` vs `lst_006` discrepancy described above. I didn't change the generated scoring logic; I updated the spec's walkthrough to match the verified real behavior instead.

**Instance 2 — `run_agent` planning loop (Milestone 4):** I gave Claude the full Architecture diagram plus the Planning Loop and State Management sections from `planning.md`, along with the numbered TODO comments in `agent.py`, and asked it to implement `run_agent()`. Before running it, I verified the generated code: it calls `_new_session()` once, parses the query before searching, checks `len(search_results) == 0` and returns early without calling `suggest_outfit`/`create_fit_card` on that branch, and only sets `selected_item` on the non-empty branch. I confirmed this by printing `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["error"]` after a run and checking they matched what was passed into the next tool call — and by running the no-results test case in `agent.py`'s `__main__` block to confirm `fit_card` stayed `None` and `error` held the specific message.

---

## Running the App

```bash
pip install -r requirements.txt
# Add GROQ_API_KEY=your_key_here to a .env file
python app.py
```

Open the URL shown in the terminal (check the output — it may not be `localhost:7860`).

## Running Tests

```bash
python -m pytest tests/ -v
```