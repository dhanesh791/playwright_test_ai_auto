from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class SemanticTarget:
    """Declarative description of a page element we want to keep stable."""

    key: str
    tag: str
    types: Sequence[str]
    hints: Sequence[str]
    required_hints: Sequence[str]


DEFAULT_TARGETS: Dict[str, SemanticTarget] = {
    "login.username": SemanticTarget(
        key="login.username",
        tag="input",
        types=("text", "email"),
        hints=("account name", "sign in", "username", "email"),
        required_hints=(),
    ),
    "login.password": SemanticTarget(
        key="login.password",
        tag="input",
        types=("password",),
        hints=("password", "sign in"),
        required_hints=("password",),
    ),
    "login.submit": SemanticTarget(
        key="login.submit",
        tag="button",
        types=("submit",),
        hints=("sign in", "log in", "login"),
        required_hints=(),
    ),
}


def load_targets(extra_targets: Dict[str, SemanticTarget] | None = None) -> Dict[str, SemanticTarget]:
    """Return the merged semantic targets dictionary."""

    merged = dict(DEFAULT_TARGETS)
    if extra_targets:
        merged.update(extra_targets)
    return merged
