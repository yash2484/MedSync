"""Stage 3 — probabilistic patient deduplication (Fellegi-Sunter).  [MANUAL]

Pure comparators + scoring + union-find clustering are unit-testable without a
database. The DB sweep at the bottom is the only part needing a session.

Healthcare safety (CLAUDE.md §6.4): false merges are worse than missed
duplicates. Possible-matches are flagged for human review, NEVER auto-merged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import log2

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


@dataclass(frozen=True)
class PatientFields:
    fhir_id: str
    last_name: str | None
    given_name: str | None
    birth_date: date | None
    gender: str | None
    address_line: str | None
    postal_code: str | None


# Fellegi-Sunter per-field (m = P(agree|match), u = P(agree|non-match)).
# Weights: agree -> log2(m/u); disagree -> log2((1-m)/(1-u)).
_FIELD_PARAMS = {
    "last_name": (0.95, 0.01),
    "given_name": (0.90, 0.02),
    "birth_date": (0.95, 0.003),
    "gender": (0.98, 0.50),
    "address": (0.85, 0.05),
    "postal_code": (0.90, 0.04),
}


def _weight(field: str, agree: bool) -> float:
    m, u = _FIELD_PARAMS[field]
    return log2(m / u) if agree else log2((1 - m) / (1 - u))


def score_pair(a: PatientFields, b: PatientFields, name_cutoff: float = 0.85) -> float:
    agreements = {
        "last_name": jaro_winkler(a.last_name, b.last_name) >= name_cutoff,
        "given_name": jaro_winkler(a.given_name, b.given_name) >= name_cutoff,
        "birth_date": exact(a.birth_date, b.birth_date) == 1.0,
        "gender": exact(a.gender, b.gender) == 1.0,
        "address": token_overlap(a.address_line, b.address_line) >= 0.5,
        "postal_code": exact(a.postal_code, b.postal_code) == 1.0,
    }
    return sum(_weight(f, agree) for f, agree in agreements.items())


def classify(score: float, upper: float, lower: float) -> str:
    if score > upper:
        return "match"
    if score >= lower:
        return "possible"
    return "non-match"
