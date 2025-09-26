from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from playwright.async_api import async_playwright

from .capture import capture_interactive_nodes
from .config import SemanticTarget, load_targets
from .scoring import (
    Embedder,
    ScoreResult,
    build_description,
    build_text_blob,
    pick_best_node,
)
from .selectors import CandidateSelector, build_candidates, select_primary, verify_candidates


def summarise_node(node: Dict[str, Any]) -> Dict[str, Any]:
    attrs = node.get("attrs", {})
    interesting = {
        k: v
        for k, v in attrs.items()
        if k in {"id", "name", "class", "data-testid", "placeholder", "aria-label"} and v
    }
    return {
        "tag": node.get("tag"),
        "type": node.get("type"),
        "attrs": interesting,
        "ancestor_texts": [anc.get("text") for anc in node.get("ancestorsDetailed", []) if anc.get("text")][:2],
    }


def bundle_entry(node: Dict[str, Any], score: ScoreResult, candidates: List[CandidateSelector]) -> Dict[str, Any]:
    primary = select_primary(candidates)
    status = "resolved" if primary else ("needs_review" if candidates else "unresolved")
    fallbacks = [c.asdict() for c in candidates if c.unique and primary and c.selector != primary.selector]

    return {
        "status": status,
        "confidence": round(score.combined_score, 2),
        "heuristic": {
            "score": score.heuristic_score,
            "max": score.heuristic_max,
            "matched_hints": list(score.matched_hints),
        },
        "embedding_similarity": round(score.embedding_similarity, 3),
        "node": summarise_node(node),
        "primary": primary.asdict() if primary else None,
        "candidates": [c.asdict() for c in candidates],
        "fallbacks": fallbacks,
    }


def prepare_nodes(nodes: List[Dict[str, Any]]) -> None:
    for node in nodes:
        node.setdefault("text_blob", build_text_blob(node))
        node.setdefault("description", build_description(node))


async def resolve_url(
    url: str,
    targets: Dict[str, SemanticTarget],
    *,
    headless: bool = True,
    model_name: str | None = None,
) -> Dict[str, Any]:
    embedder = Embedder(model_name) if model_name else Embedder()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        nodes = await capture_interactive_nodes(page)
        prepare_nodes(nodes)

        resolution: Dict[str, Any] = {}
        for key, target in targets.items():
            node, score = pick_best_node(nodes, target, embedder)
            if not node or not score:
                resolution[key] = {
                    "status": "unresolved",
                    "message": "No candidate matched semantic hints",
                    "target": asdict(target),
                }
                continue
            candidates = build_candidates(node)
            await verify_candidates(page, candidates)
            entry = bundle_entry(node, score, candidates)
            resolution[key] = entry

        await browser.close()

    return {
        "url": url,
        "semantic_targets": list(targets.keys()),
        "resolution": resolution,
    }


# ----------------------------- discovery mode helpers -----------------------------

_LABEL_FIELDS = (
    "ariaLabel",
    "placeholder",
    "innerText",
    "textContent",
)


def _label_candidates(node: Dict[str, Any]) -> List[str]:
    labels = node.get("labels", []) or []
    values = list(labels)
    attrs = node.get("attrs", {})
    for field in _LABEL_FIELDS:
        value = node.get(field)
        if value:
            values.append(value)
        attr_val = attrs.get(field)
        if attr_val:
            values.append(attr_val)
    return [v.strip() for v in values if isinstance(v, str) and v.strip()]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or ""


def _auto_key(node: Dict[str, Any], index: int, counters: Dict[str, int]) -> str:
    base = ""
    for candidate in _label_candidates(node):
        base = _slugify(candidate)
        if base:
            break
    if not base:
        tag = node.get("tag", "node")
        input_type = node.get("type") or "generic"
        base = _slugify(f"{tag}_{input_type}")
    if not base:
        base = f"node_{index + 1}"

    count = counters.get(base, 0)
    counters[base] = count + 1
    if count == 0:
        return base
    return f"{base}_{count + 1}"


def _confidence_from_primary(primary: CandidateSelector) -> float:
    description = (primary.description or "").lower()
    selector = primary.selector.lower()
    if "id attribute" in description or selector.startswith("css=#"):
        return 1.0
    if "data-" in selector:
        return 0.95
    if "name attribute" in description:
        return 0.9
    if selector.startswith("role="):
        return 0.85
    if "ancestor class" in description:
        return 0.7
    return 0.6


async def discover_all(
    url: str,
    *,
    headless: bool = True,
) -> Dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        nodes = await capture_interactive_nodes(page)
        prepare_nodes(nodes)

        resolution: Dict[str, Any] = {}
        counters: Dict[str, int] = {}

        for index, node in enumerate(nodes):
            candidates = build_candidates(node)
            await verify_candidates(page, candidates)
            primary = select_primary(candidates)
            if not primary:
                continue
            confidence = round(_confidence_from_primary(primary), 2)
            key = _auto_key(node, index, counters)
            fallbacks = [c.asdict() for c in candidates if c.unique and c.selector != primary.selector]
            resolution[key] = {
                "status": "resolved",
                "confidence": confidence,
                "heuristic": None,
                "embedding_similarity": None,
                "node": summarise_node(node),
                "primary": primary.asdict(),
                "candidates": [c.asdict() for c in candidates],
                "fallbacks": fallbacks,
            }

        await browser.close()

    return {
        "url": url,
        "semantic_targets": list(resolution.keys()),
        "resolution": resolution,
    }


# ----------------------------- output helpers -----------------------------

def write_json_bundle(bundle: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2)


def write_playwright_assets(bundle: Dict[str, Any], ts_path: Path, spec_path: Path, url: str) -> None:
    resolution = bundle.get("resolution", {})
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.parent.mkdir(parents=True, exist_ok=True)

    entries_lines: List[str] = []
    keys: List[str] = []
    for key, payload in resolution.items():
        primary = payload.get("primary")
        if not primary or not primary.get("selector"):
            continue
        keys.append(key)
        fallbacks = [cand.get("selector") for cand in payload.get("fallbacks", []) if cand.get("selector")]
        selector_literal = json.dumps(primary["selector"])
        fallbacks_literal = ", ".join(json.dumps(fb) for fb in fallbacks)
        entry = (
            f"  '{key}': {{\n"
            f"    selector: {selector_literal},\n"
            f"    confidence: {payload.get('confidence', 0.0)},\n"
            f"    fallbacks: [{fallbacks_literal}]\n"
            "  }"
        )
        entries_lines.append(entry)

    keys_literal = " | ".join(f"'{key}'" for key in keys) or "never"
    dict_literal = ",\n".join(entries_lines)

    ts_content = (
        "// Auto-generated by locator_ai. Do not edit manually.\n"
        "import type { Page } from '@playwright/test';\n\n"
        f"type SemanticKey = {keys_literal};\n\n"
        "type LocatorEntry = {\n"
        "  selector: string;\n"
        "  confidence: number;\n"
        "  fallbacks: string[];\n"
        "};\n\n"
        "export const locatorBundle: Record<SemanticKey, LocatorEntry> = {\n"
        f"{dict_literal}\n"
        "} as const;\n\n"
        "export function getLocator(page: Page, key: SemanticKey) {\n"
        "  const entry = locatorBundle[key];\n"
        "  if (!entry) {\n"
        "    throw new Error('Unknown semantic key: ' + key);\n"
        "  }\n"
        "  return page.locator(entry.selector);\n"
        "}\n"
    )
    ts_path.write_text(ts_content, encoding="utf-8")

    spec_content = (
        "// Auto-generated sample Playwright test using locator_ai bundle.\n"
        "import { test, expect } from '@playwright/test';\n"
        "import { getLocator, locatorBundle } from '../locators.generated';\n\n"
        "test('generated selectors resolve', async ({ page }) => {\n"
        f"  await page.goto('{url}');\n"
        "  for (const key of Object.keys(locatorBundle) as Array<keyof typeof locatorBundle>) {\n"
        "    const locator = getLocator(page, key);\n"
        "    await expect(locator).toBeVisible();\n"
        "  }\n"
        "});\n"
    )
    spec_path.write_text(spec_content, encoding="utf-8")


# ----------------------------- CLI wiring -----------------------------

def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Locator AI CLI")
    parser.add_argument("--url", default="https://store.steampowered.com/login/?redir=&redir_ssl=1", help="Target page URL")
    parser.add_argument("--out", default="artifacts/locator-bundle.json", help="Path to write the JSON bundle")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Sentence transformer model name")
    parser.add_argument("--no-headless", action="store_true", help="Run browser with a UI window (debug)")
    parser.add_argument("--update-playwright", action="store_true", help="Generate Playwright helper assets")
    parser.add_argument("--playwright-ts", default="playwright/locators.generated.ts", help="Path to generated Playwright helper")
    parser.add_argument("--playwright-spec", default="playwright/tests/login.generated.spec.ts", help="Path to generated Playwright spec")
    parser.add_argument("--discover-all", action="store_true", help="Generate selectors for every interactive element without predefined semantic keys")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    if args.discover_all:
        bundle = asyncio.run(
            discover_all(
                url=args.url,
                headless=not args.no_headless,
            )
        )
    else:
        targets = load_targets()
        bundle = asyncio.run(
            resolve_url(
                url=args.url,
                targets=targets,
                headless=not args.no_headless,
                model_name=args.model,
            )
        )

    write_json_bundle(bundle, Path(args.out))

    if args.update_playwright:
        write_playwright_assets(bundle, Path(args.playwright_ts), Path(args.playwright_spec), args.url)

    print(json.dumps(bundle, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
