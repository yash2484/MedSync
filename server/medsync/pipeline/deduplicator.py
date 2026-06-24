"""Stage 3 — probabilistic patient deduplication (Fellegi-Sunter).  [MANUAL]

Pure comparators + scoring + union-find clustering are unit-testable without a
database. The DB sweep at the bottom is the only part needing a session.

Healthcare safety (CLAUDE.md §6.4): false merges are worse than missed
duplicates. Possible-matches are flagged for human review, NEVER auto-merged.
"""
from __future__ import annotations

import jellyfish


def soundex_block_key(last_name: str | None, birth_year: int | None) -> str:
    if last_name is None and birth_year is None:
        return "____"
    code = jellyfish.soundex(last_name) if last_name else "____"
    year = str(birth_year) if birth_year else "____"
    return f"{code}:{year}"


def jaro_winkler(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return jellyfish.jaro_winkler_similarity(a.lower(), b.lower())


def token_overlap(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def exact(a, b) -> float:
    if a is None or b is None:
        return 0.0
    return 1.0 if a == b else 0.0
