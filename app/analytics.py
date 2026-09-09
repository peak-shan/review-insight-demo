"""Explainable bilingual keyword frequencies and sentiment classification."""

import re
from collections import Counter
from typing import Literal, TypedDict

import jieba

STOPWORDS = set("的 了 是 我 很 也 都 和 与 在 有 这 个 一 件 买 穿 就 还 但 不 太 非常 比较 一个 这个 这件 衣服 the a an and or is are was were i my it this that to of for in on with but very so as its".split())
POSITIVE = ("舒服", "舒适", "合身", "柔软", "喜欢", "满意", "好看", "透气", "保暖", "推荐", "great", "good", "comfortable", "soft", "perfect", "love", "excellent")
NEGATIVE = ("失望", "差", "扎人", "掉色", "缩水", "破损", "起球", "难看", "太小", "太大", "bad", "poor", "uncomfortable", "scratchy", "terrible", "disappointed", "tight")


class WordFrequency(TypedDict):
    """A keyword and its occurrence count."""

    word: str
    count: int


class AnalysisResult(TypedDict):
    """Counts and fractions over nonempty reviews; ratios range from 0 to 1."""

    total: int
    top_words: list[WordFrequency]
    positive_top_words: list[WordFrequency]
    negative_top_words: list[WordFrequency]
    positive: int
    negative: int
    neutral: int
    positive_ratio: float
    negative_ratio: float


def keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    """Count distinct matching keywords, respecting English word boundaries."""
    return sum(
        bool(re.search(rf"\b{re.escape(word)}\b", text))
        if word.isascii() else word in text
        for word in keywords
    )


def top_words(comments: list[str]) -> list[WordFrequency]:
    """Return Top20 using the same tokenization and stopwords for every corpus."""
    counts: Counter[str] = Counter()
    for comment in comments:
        text = comment.strip().lower()
        counts.update(
            word for token in jieba.cut(text)
            if (word := token.strip()) not in STOPWORDS
            and re.fullmatch(r"[a-z]+|[\u4e00-\u9fff]+", word)
        )
    return [{"word": word, "count": count} for word, count in counts.most_common(20)]


def classify_review(comment: str) -> Literal["positive", "negative", "neutral"]:
    """Classify general review text; ties and no keyword hits are neutral."""
    text = comment.strip().lower()
    score = keyword_hits(text, POSITIVE) - keyword_hits(text, NEGATIVE)
    return "positive" if score > 0 else "negative" if score < 0 else "neutral"


def summarize_corpora(
    positive: list[str], negative: list[str], neutral: list[str]
) -> AnalysisResult:
    """Summarize nonempty text cells; ratios include neutral in the denominator."""
    total = len(positive) + len(negative) + len(neutral)
    return {
        "total": total,
        "top_words": top_words(positive + negative + neutral),
        "positive_top_words": top_words(positive),
        "negative_top_words": top_words(negative),
        "positive": len(positive), "negative": len(negative), "neutral": len(neutral),
        "positive_ratio": len(positive) / total if total else 0.0,
        "negative_ratio": len(negative) / total if total else 0.0,
    }


def analyze_reviews(comments: list[str]) -> AnalysisResult:
    """Classify general comments and reuse the common corpus summary function."""
    corpora: dict[str, list[str]] = {"positive": [], "negative": [], "neutral": []}
    for comment in comments:
        if text := comment.strip():
            corpora[classify_review(text)].append(text)
    return summarize_corpora(corpora["positive"], corpora["negative"], corpora["neutral"])
