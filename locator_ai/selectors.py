from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from playwright.async_api import Page

ATTR_PRIORITY = [
    "data-testid",
    "data-test",
    "data-qa",
    "data-qa-id",
    "data-automation-id",
    "id",
    "name",
    "aria-label",
    "placeholder",
    "ng-model",
]


@dataclass
class CandidateSelector:
    selector: str
    strategy: str
    description: str
    count: Optional[int] = None
    unique: Optional[bool] = None
    error: Optional[str] = None

    def asdict(self) -> Dict:
        return asdict(self)


def _escape_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _attribute_selectors(node: Dict) -> List[CandidateSelector]:
    tag = node.get("tag", "")
    attrs = node.get("attrs", {})
    selectors: List[CandidateSelector] = []

    for attr in ATTR_PRIORITY:
        value = attrs.get(attr)
        if not value:
            continue
        if attr == "id":
            selectors.append(
                CandidateSelector(
                    selector=f"css=#{_escape_value(value)}",
                    strategy="css",
                    description="id attribute",
                )
            )
        else:
            selectors.append(
                CandidateSelector(
                    selector=f"css={tag}[{attr}=\"{_escape_value(value)}\"]",
                    strategy="css",
                    description=f"{attr} attribute",
                )
            )
    return selectors


def _ancestor_selectors(node: Dict) -> List[CandidateSelector]:
    tag = node.get("tag", "")
    node_type = node.get("type")
    attr_clause = f"[type=\"{_escape_value(node_type)}\"]" if node_type else ""
    selectors: List[CandidateSelector] = []
    seen_text_keys = set()

    for anc in node.get("ancestorsDetailed", []):
        classes = anc.get("classes", [])
        if classes:
            compact = anc["tag"] + "".join(f".{cls}" for cls in classes[:2])
            selectors.append(
                CandidateSelector(
                    selector=f"css={compact} {tag}{attr_clause}",
                    strategy="css",
                    description=f"ancestor class {classes[0] if classes else anc['tag']}",
                )
            )
        text = anc.get("text", "")
        if text and "\n" not in text and len(text) <= 80:
            key = text.lower()
            if key not in seen_text_keys:
                escaped = text.replace('"', '\\"')
                selectors.append(
                    CandidateSelector(
                        selector=f"css={anc['tag']}:has-text(\"{escaped}\") >> css={tag}{attr_clause}",
                        strategy="css",
                        description=f"ancestor text contains '{text[:30]}'",
                    )
                )
                seen_text_keys.add(key)
    return selectors


def _role_selectors(node: Dict) -> List[CandidateSelector]:
    selectors: List[CandidateSelector] = []
    tag = node.get("tag")
    inner = node.get("innerText")
    role = node.get("role")
    if tag == "button" and inner:
        escaped = inner.replace('"', '\\"')
        selectors.append(
            CandidateSelector(
                selector=f"role=button[name=\"{escaped}\"]",
                strategy="role",
                description="button accessible name",
            )
        )
        selectors.append(
            CandidateSelector(
                selector=f"text={inner}",
                strategy="text",
                description="text matcher",
            )
        )
    if role and inner:
        escaped = inner.replace('"', '\\"')
        selectors.append(
            CandidateSelector(
                selector=f"role={role}[name=\"{escaped}\"]",
                strategy="role",
                description="ARIA role + name",
            )
        )
    return selectors


def build_candidates(node: Dict) -> List[CandidateSelector]:
    ordered: List[CandidateSelector] = []
    seen = set()
    for builder in (_attribute_selectors, _ancestor_selectors, _role_selectors):
        for candidate in builder(node):
            if candidate.selector in seen:
                continue
            seen.add(candidate.selector)
            ordered.append(candidate)
    return ordered


async def verify_candidates(page: Page, candidates: List[CandidateSelector]) -> None:
    for candidate in candidates:
        try:
            locator = page.locator(candidate.selector)
            count = await locator.count()
            candidate.count = count
            candidate.unique = count == 1
        except Exception as exc:
            candidate.error = str(exc)
            candidate.count = None
            candidate.unique = False


def select_primary(candidates: List[CandidateSelector]) -> Optional[CandidateSelector]:
    for candidate in candidates:
        if candidate.unique:
            return candidate
    return None
