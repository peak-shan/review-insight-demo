"""Configurable, normalized substring rules for bilingual column roles."""

import unicodedata
from typing import Literal, TypedDict

ColumnRole = Literal["positive", "negative", "general", "requirement"]


class ColumnRule(TypedDict):
    """Keywords to include and exclude when matching a normalized header."""

    include: tuple[str, ...]
    exclude: tuple[str, ...]


COLUMN_RULES: dict[ColumnRole, ColumnRule] = {
    "negative": {"include": ("差评", "差评点", "负面", "negative", "bad"), "exclude": ()},
    "positive": {"include": ("好评", "好评点", "正面", "positive", "good"), "exclude": ("差评", "负面")},
    "requirement": {"include": ("需求", "建议", "expect"), "exclude": ()},
    "general": {"include": ("评论", "评价", "comment", "review", "content", "买家留言", "feedback"), "exclude": ()},
}


def normalize_column(column: str) -> str:
    """Lowercase and remove punctuation/spacing, retaining Unicode letters/numbers."""
    return "".join(char for char in unicodedata.normalize("NFKC", column).lower() if char.isalnum())


def identify_column(column: str) -> ColumnRole | None:
    """Choose one role in rule order: negative, positive, requirement, general."""
    normalized = normalize_column(column)
    for role, rule in COLUMN_RULES.items():
        if any(normalize_column(word) in normalized for word in rule["include"]) and not any(
            normalize_column(word) in normalized for word in rule["exclude"]
        ):
            return role
    return None
