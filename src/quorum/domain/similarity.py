"""Finds questions that were probably already asked, as someone types.

TF-IDF with cosine similarity: words that are rare across the session ("migrations", "rust")
count for much more than common ones ("how", "do", "think"). Small, dependency-free and
explainable, which matters more here than the last few points of accuracy.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    """a about after all also am an and any anyone are as at be been being but by can could did
    do does doing for from get got had has have how i if in into is it its just me more most my
    no not of on or our out over please should so some than that the their them then there these
    they think this to too us very was we were what when where which who why will with would you
    your""".split()  # noqa: SIM905  # a word block is easier to read and edit than a list
)


def _stem(word: str) -> str:
    """Light suffix stripping: 'migrations', 'migrating' and 'migrated' meet at 'migrat'."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    for suffix in ("ing", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def terms(text: str) -> list[str]:
    return [
        _stem(word)
        for word in _WORD.findall(text.lower())
        if len(word) > 1 and word not in STOPWORDS
    ]


@dataclass(frozen=True, slots=True)
class Match[K]:
    key: K
    score: float


def find_similar[K](
    query: str,
    candidates: Sequence[tuple[K, str]],
    *,
    limit: int = 3,
    threshold: float = 0.3,
) -> list[Match[K]]:
    query_terms = terms(query)
    if not query_terms or not candidates:
        return []

    documents = [terms(text) for _, text in candidates]
    frequency = Counter(term for document in documents for term in set(document))
    total = len(documents) + 1

    def weights(document: list[str]) -> dict[str, float]:
        counts = Counter(document)
        vector = {
            term: count * (math.log((1 + total) / (1 + frequency[term])) + 1.0)
            for term, count in counts.items()
        }
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        return {term: weight / norm for term, weight in vector.items()} if norm else {}

    query_vector = weights(query_terms)
    matches: list[Match[K]] = []
    for (key, _), document in zip(candidates, documents, strict=True):
        document_vector = weights(document)
        score = sum(w * document_vector.get(term, 0.0) for term, w in query_vector.items())
        if score >= threshold:
            matches.append(Match(key, score))
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches[:limit]
