"""Entity-overlap dedup: is a candidate article the same story as one already seen?

Pure set comparison — no natasha dependency here — so it's cheap to call per candidate and easy
to unit test in isolation from `entities.EntityExtractor`.
"""

from collections.abc import Iterable


def is_duplicate(
    entities: list[str], others: Iterable[list[str]], *, threshold: float, min_shared: int
) -> bool:
    """True if `entities` overlaps any set in `others` past `threshold` Jaccard similarity.

    `min_shared` guards against false positives between two sparse-entity (or entity-less)
    articles, where a small shared set can clear a similarity threshold on its own.
    """
    candidate = set(entities)
    if len(candidate) < min_shared:
        return False

    for other in others:
        other_set = set(other)
        shared = candidate & other_set
        if len(shared) < min_shared:
            continue
        union = candidate | other_set
        if union and len(shared) / len(union) >= threshold:
            return True
    return False
