# Locator AI Architecture

## Problem
- Playwright tests currently depend on brittle CSS selectors such as coverNoteType = "#COVER_NOTE_TYPE_ID".
- Frontend releases regularly rename id and 
g-model attributes, breaking tests and creating manual triage work.
- QA engineers need a repeatable mechanism to regenerate selectors across environments without hand-editing scripts.

## Goals
- Treat selector names (coverNoteType, ehicleType, etc.) as stable semantic identifiers owned by QA.
- Automatically reconcile each semantic identifier with the best available selector in the latest build.
- Provide CI feedback when confidence drops, plus tooling to approve or correct regenerated locators.
- Keep the flow Playwright-friendly: expose an API or config bundle consumed by page.getByTestId-style helpers.

## System Overview
1. **State Capture** – Harvest DOM, accessibility tree, and rendered context during scripted crawls or Playwright trace runs.
2. **Feature Extraction** – Normalize each DOM node into a rich feature vector (attributes, textual cues, layout, neighbor info, vision crop).
3. **Semantic Locator KB** – Persist the per-element feature history keyed by QA semantic IDs.
4. **Locator Resolver** – Match an incoming page state against the KB, regenerate candidate selectors, and rank them via rules + LLM.
5. **Verification & Publishing** – Replay candidates in a headless browser, score confidence, emit updated locator bundles, surface low-confidence diffs.

The DeploySentinel Recorder project shows how to instrument browsers for event+selector capture and can inform the State Capture component below.

## Components
### 1. State Capture Layer
- **Playwright hook**: Add a global fixture that, after each navigation, runs document.querySelectorAll('*') in the page sandbox and collects the top-level markup, ARIA roles, labels, and computed styles (limited subset).
- **Recorder-based ingest**: Similar to DeploySentinel Recorder, run a Chromium extension (or Playwright's "record" mode) to log user flows. Each captured event contributes DOM snapshots and the recorder's best-effort selector hints.
- **Screenshot slices**: Capture full-page or element-specific screenshots so vision models can disambiguate visually similar nodes.

### 2. Feature Extraction
- Clean & hash attribute sets: id, class, data-*, Angular bindings, labels, placeholder, ria-*.
- Text embeddings: encode visible text and accessible names with a lightweight sentence transformer.
- DOM graph features: parent/child tags, sibling order, relative XPath depth, CSS nth-of-type.
- Visual embeddings (optional phase 2): run crops through a small vision model (e.g., CLIP) to distinguish repeated buttons.

### 3. Semantic Locator Knowledge Base
- Seed using today's locator map – map each key to its resolved DOM node and store the extracted feature vector + selector history.
- Track versioned snapshots: {semanticId, buildId, featureHash, selectors[], confidence}.
- Support annotations (human overrides, "never use text contains" flags).
- Allow multiple acceptable selectors per semantic key for variant layouts.

### 4. Locator Resolver Service
- **Input**: semantic key + latest build DOM dump.
- **Matching**: 
  1. Rule-based narrowing (exact attribute matches, role + text, unique data-testid).
  2. Similarity search over the KB embeddings (FAISS or vector DB) to shortlist candidates despite attribute drift.
  3. LLM ranker (fine-tuned on historical resolutions) that takes the semantic key, previous selector, and candidate HTML, then outputs the most plausible unique selector plus fallbacks.
- **Output**: Structured bundle {"primary": "locator", "fallbacks": ["locator"], "confidence": 0.93}.

### 5. Verification, Feedback, Publishing
- Replay proposed selectors in a headless Playwright run; confirm uniqueness via page.locator(candidate).count() === 1.
- Score confidence using feature similarity, verification result, and historical stability.
- Publish success cases to a versioned artifact (JSON/YAML) consumed by Playwright helper functions (e.g., locatorBundle.get('coverNoteType')).
- Queue low-confidence cases for human review via a lightweight UI. Approved selections feed back into the KB.

## Data Flow
`
Playwright Trace / Recorder Logs
          ↓
   State Capture (DOM + metadata)
          ↓
 Feature Extraction → Semantic KB (vector + history store)
          ↓
   Locator Resolver (rules + ANN + LLM)
          ↓
 Verification Harness (Playwright headless)
          ↓
 Locator Bundle (CI artifact) + Review Queue
`

## Integration with Playwright Tests
- Provide a custom helper, e.g. const checkoutButton = locatorStore.get('coverNoteType', page); that loads the latest bundle once per test run.
- Bundle is cached locally; updates happen via CI pull request or artifact download during pipeline bootstrap.
- Tests only reference semantic keys, shielding them from selector churn.

## Implementation Roadmap
1. **Bootstrap dataset**
   - Instrument Playwright smoke tests to emit DOM dumps + the current hard-coded selectors.
   - Backfill the KB with the manager-supplied map and confirm we can resolve each entry in a baseline build.
2. **Heuristic baseline**
   - Build a resolver that relies purely on deterministic features (IDs, data-*, text matches with thresholds) to prove the pipeline.
   - Surface diffs via CI comment/JSON artifact.
3. **LLM-assisted resolver**
   - Prepare training pairs: (semantic key, old selector, candidate nodes) → desired selector.
   - Fine-tune or prompt a small language model (LLM) to pick the best locator format, using DeploySentinel's selector heuristics as priors.
   - Add confidence scoring & review UI.
4. **Continuous learning**
   - Record production user flows (or nightly crawls) with a recorder extension to expand coverage beyond test scripts.
   - Feed approved human corrections back into the KB + fine-tune data.
5. **Tooling polish**
   - CLI for QA to query the bundle (locator-ai inspect coverNoteType).
   - Visual diff UI showing old vs new element screenshot/snippet to speed up approvals.

## Using DeploySentinel Recorder as Inspiration
- Reuse their approach to capture user events and their best-effort selector list; each recorded selector becomes an extra label in the KB.
- Extend the recorder to export DOM HTML, relevant attributes, and page screenshots to our ingestion service.
- Adopt their UX patterns (overlay, "copy code") for the human review tool so QA sees familiar workflows.

## Risks & Mitigations
- **Model hallucination**: keep rule-based guards; never ship a locator without deterministic verification in a real browser context.
- **Performance**: caching DOM feature extraction results per page reduces reprocessing in CI.
- **Front-end rebuild frequency**: ensure ingestion runs on every PR or nightly build so drift is caught before merges.
- **Security**: DOM dumps may contain PII; scrub sensitive inputs (password fields, tokens) during capture.

## Deliverables Per Phase
- Phase 1: DOM capture scripts, KB schema, baseline resolver, JSON bundle wired into Playwright helper.
- Phase 2: LLM ranking service with confidence metrics, CI integration, human-in-loop UI.
- Phase 3: Vision enhancements, analytics (flakiness dashboards), auto-generated change summaries.
