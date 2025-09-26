# Locator AI Toolkit

This project automates Playwright locator maintenance by combining page
introspection, heuristic scoring, and a lightweight embedding model. The
`locator_ai` package fetches locators from any URL, ranks the best candidates,
verifies them in a live browser, and updates Playwright assets automatically.

## Prerequisites
1. Create a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   python -m pip install --upgrade pip
   python -m pip install playwright sentence-transformers
   python -m playwright install chromium
   ```
2. (Optional) cache the Playwright browser bundle in CI via
   `%USERPROFILE%\AppData\Local\ms-playwright`.

## Generate a locator bundle
Run the CLI (either through `python -m locator_ai` or
`python prototype\locator_probe.py`, which proxies to the same entry point):
```powershell
python -m locator_ai --url "https://store.steampowered.com/login/?redir=&redir_ssl=1" \
  --out artifacts\steam-locators.json \
  --update-playwright
```

Common flags:
- `--url`: page to scan. Defaults to the Steam login supplied earlier.
- `--out`: path for the JSON bundle (defaults to `artifacts/locator-bundle.json`).
- `--model`: embedding model (defaults to
  `sentence-transformers/all-MiniLM-L6-v2`).
- `--no-headless`: open Chromium visibly for debugging.
- `--update-playwright`: emit helper files
  (`playwright/locators.generated.ts`, `playwright/tests/login.generated.spec.ts`).
- `--discover-all`: skip predefined semantic keys and derive selectors for every
  interactive element (inputs, buttons, selects, textareas) on the page.

Example: bulk discover every locator on Random.org’s login page and regenerate
the helper assets:
```powershell
python -m locator_ai --url "https://accounts.random.org/" \
  --out artifacts\random-discover.json \
  --update-playwright \
  --discover-all
```

## Bundle structure
Every run emits JSON like:
```json
{
  "url": "https://store.steampowered.com/login/?redir=&redir_ssl=1",
  "semantic_targets": ["login.username", "login.password", "login.submit"],
  "resolution": {
    "login.username": {
      "status": "resolved",
      "confidence": 0.74,
      "heuristic": {
        "score": 10,
        "max": 14,
        "matched_hints": ["account name", "sign in"]
      },
      "embedding_similarity": 0.771,
      "primary": {
        "selector": "css=div._3BkiHun-mminuTO-Y-zXke input[type=\"text\"]",
        "strategy": "css",
        "unique": true
      },
      "fallbacks": [
        { "selector": "css=form._2v60tM463fW0V7GDe92E5f input[type=\"text\"]", "unique": true }
      ],
      "candidates": [ ... full diagnostics ... ]
    }
  }
}
```
Key fields:
- `confidence`: combined heuristic + embedding score (0–1). In discovery mode
  this reflects selector quality heuristics.
- `embedding_similarity`: raw cosine similarity from the transformer model (null
  in discovery mode, because no semantic key was supplied).
- `primary`: first selector that Playwright confirmed is unique on the page.
- `fallbacks`: additional verified selectors the helper can fall back to.
- `candidates`: every selector attempt, including counts and Playwright errors
  for debugging.
- `status`: `resolved`, `needs_review`, or `unresolved` depending on whether a
  unique selector was found.

## Playwright integration
When `--update-playwright` is supplied the CLI produces:
- `playwright/locators.generated.ts` exporting `locatorBundle` and
  `getLocator(page, semanticKey)`. Tests can now call `getLocator(page, key)`
  instead of hard-coding selectors.
- `playwright/tests/login.generated.spec.ts` as a sample spec. In discovery
  mode the spec iterates over every generated key to ensure all locators load.

These files rebuild on every CLI run, so commit them (or publish as artifacts)
if you want the test suite to pick up the latest selectors.

## How it works
1. **Capture**: Load the page with Playwright, capturing every `input`, `button`,
   `select`, and `textarea`, plus attributes, labels, nearby text, ancestor
   classes, and form metadata (`locator_ai.capture`).
2. **Score**: For semantic-key mode, combine deterministic heuristics
   (tag/type + keyword hints) with an embedding similarity check derived from
   `sentence-transformers/all-MiniLM-L6-v2` (`locator_ai.scoring`).
3. **Generate selectors**: Build CSS/role/text candidates from attributes and
   ancestors (`locator_ai.selectors`).
4. **Verify**: Replay each candidate in the live DOM; keep the first unique
   match as the primary selector and retain other unique matches as fallbacks.
5. **Publish**: Emit JSON + Playwright helper files so the test suite can load
   selectors by semantic name (or auto-generated keys when using discovery).

## Next steps
- Extend `locator_ai/config.py` with more semantic keys (e.g.,
  `login.rememberMe`, `login.forgotLink`) and rerun the CLI to widen coverage.
- Persist the captured node blobs to a knowledge base so historical selectors
  inform future matches (feeds into `docs/locator-ai-architecture.md`).
- Swap the off-the-shelf sentence transformer for a fine-tuned embedding model
  or LLM reranker once you have labeled resolutions.
- Integrate the CLI into CI to regenerate locators on every PR and gate merges
  when `status` becomes `needs_review`/`unresolved`.
