from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer, util

from .config import SemanticTarget


@dataclass
class ScoreResult:
    heuristic_score: float
    heuristic_max: float
    matched_hints: Sequence[str]
    embedding_similarity: float
    combined_score: float


def build_text_blob(node: Dict) -> str:
    parts: List[str] = []
    attrs = node.get("attrs", {})
    parts.extend(val for val in attrs.values() if val)
    parts.extend(node.get("labels", []))
    parts.append(node.get("innerText", ""))
    parts.append(node.get("textContent", ""))
    for sibling in node.get("siblingTexts", []):
        parts.append(sibling.get("text", ""))
    for anc in node.get("ancestorsDetailed", []):
        parts.append(anc.get("text", ""))
        parts.extend(anc.get("classes", []))
    return " ".join(p for p in parts if p).lower()


def build_description(node: Dict) -> str:
    attrs = node.get("attrs", {})
    parts: List[str] = [
        f"tag={node.get('tag')}",
        f"type={node.get('type')}",
    ]
    for key in ("id", "name", "class", "data-testid", "placeholder", "aria-label"):
        value = attrs.get(key)
        if value:
            parts.append(f"{key}={value}")
    if node.get("labels"):
        parts.append("labels=" + "|".join(node["labels"]))
    if node.get("innerText"):
        parts.append(f"inner={node['innerText']}")
    if node.get("textContent") and node.get("textContent") != node.get("innerText"):
        parts.append(f"textContent={node['textContent']}")
    ancestors = node.get("ancestorsDetailed", [])
    if ancestors:
        summary = " | ".join(filter(None, [anc.get("text", "") for anc in ancestors[:2]]))
        if summary:
            parts.append(f"ancestors={summary}")
    return " ; ".join(parts)


class Embedder:
    """Lazy loader for sentence transformer embeddings."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if not self._model:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @lru_cache(maxsize=256)
    def encode(self, text: str) -> np.ndarray:
        return self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)

    def similarity(self, a: str, b: str) -> float:
        emb_a = self.encode(a)
        emb_b = self.encode(b)
        return float(np.dot(emb_a, emb_b))


def score_node(node: Dict, target: SemanticTarget, embedder: Embedder | None) -> ScoreResult:
    blob = node.setdefault("text_blob", build_text_blob(node))
    description = node.setdefault("description", build_description(node))

    score = 0
    max_score = 0
    matched_hints: List[str] = []

    if target.tag:
        max_score += 3
        if node.get("tag") == target.tag:
            score += 3
    if target.types:
        max_score += 3
        if node.get("type") in target.types:
            score += 3

    required_hints = [hint.lower() for hint in target.required_hints]
    if any(hint not in blob for hint in required_hints):
        max_score += len(target.hints) * 2
        return ScoreResult(
            heuristic_score=0,
            heuristic_max=max_score or 1,
            matched_hints=(),
            embedding_similarity=0.0,
            combined_score=0.0,
        )

    hints = [hint.lower() for hint in target.hints]
    for hint in hints:
        max_score += 2
        if hint in blob:
            score += 2
            matched_hints.append(hint)

    heuristic_norm = score / (max_score or 1)
    embedding_similarity = 0.0
    if embedder:
        target_prompt = f"{target.key} element with hints: {'; '.join(target.hints)}"
        embedding_similarity = embedder.similarity(target_prompt, description)
        embedding_similarity = max(0.0, min(1.0, (embedding_similarity + 1) / 2))

    combined = round(heuristic_norm * 0.6 + embedding_similarity * 0.4, 4)

    return ScoreResult(
        heuristic_score=score,
        heuristic_max=max_score or 1,
        matched_hints=matched_hints,
        embedding_similarity=embedding_similarity,
        combined_score=combined,
    )


def pick_best_node(nodes: Iterable[Dict], target: SemanticTarget, embedder: Embedder | None) -> Tuple[Dict | None, ScoreResult | None]:
    best_node = None
    best_score: ScoreResult | None = None
    for node in nodes:
        score = score_node(node, target, embedder)
        if score.combined_score <= 0:
            continue
        if not best_score or score.combined_score > best_score.combined_score:
            best_node, best_score = node, score
    return best_node, best_score
