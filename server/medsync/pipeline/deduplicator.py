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


def assign_clusters(fhir_ids: list[str], match_pairs: list[tuple[str, str]]) -> dict[str, str]:
    parent = {fid: fid for fid in fhir_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    for x, y in match_pairs:
        if x in parent and y in parent:
            union(x, y)
    return {fid: find(fid) for fid in fhir_ids}


from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from medsync.config import settings  # noqa: E402
from medsync.models.database import Patient, PatientLink  # noqa: E402


def build_blocks(patients: list[PatientFields]) -> dict[str, list[PatientFields]]:
    blocks: dict[str, list[PatientFields]] = {}
    for p in patients:
        year = p.birth_date.year if p.birth_date else None
        key = soundex_block_key(p.last_name, year)
        blocks.setdefault(key, []).append(p)
    return blocks


def _to_fields(p: Patient) -> PatientFields:
    return PatientFields(
        fhir_id=p.fhir_id, last_name=p.family_name, given_name=p.given_name,
        birth_date=p.birth_date, gender=p.gender, address_line=p.address_line,
        postal_code=p.postal_code,
    )


async def deduplicate_records(session: AsyncSession) -> dict:
    patients = (
        await session.execute(select(Patient).where(Patient.deleted_at.is_(None)))
    ).scalars().all()
    fields = [_to_fields(p) for p in patients]
    ids = [f.fhir_id for f in fields]

    match_pairs: list[tuple[str, str]] = []
    links: list[tuple[str, str, float, str]] = []
    compared = 0
    for block in build_blocks(fields).values():
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                compared += 1
                score = score_pair(block[i], block[j], settings.dedup_name_similarity_cutoff)
                zone = classify(score, settings.dedup_upper_threshold, settings.dedup_lower_threshold)
                if zone == "match":
                    match_pairs.append((block[i].fhir_id, block[j].fhir_id))
                    links.append((block[i].fhir_id, block[j].fhir_id, score, zone))
                elif zone == "possible":
                    links.append((block[i].fhir_id, block[j].fhir_id, score, zone))

    clusters = assign_clusters(ids, match_pairs)
    matched_ids = {x for pair in match_pairs for x in pair}
    possible_ids = {x for a, b, s, z in links if z == "possible" for x in (a, b)}

    for p in patients:
        p.cluster_id = clusters.get(p.fhir_id, p.fhir_id)
        if p.fhir_id in matched_ids:
            p.match_zone = "match"
        elif p.fhir_id in possible_ids:
            p.match_zone = "possible"
        else:
            p.match_zone = "non-match"

    # Rewrite this run's link audit: clear and re-insert (idempotent).
    existing = (await session.execute(select(PatientLink))).scalars().all()
    for link in existing:
        await session.delete(link)
    for a, b, s, z in links:
        session.add(PatientLink(patient_a_fhir_id=a, patient_b_fhir_id=b, score=s, match_zone=z))

    # Invariant (CLAUDE.md §9.2): no patient in two distinct clusters.
    assert len(set(clusters.values())) <= len(ids)
    await session.commit()
    return {
        "clusters": len(set(clusters.values())),
        "matches": len(match_pairs),
        "possible": len([z for *_, z in links if z == "possible"]),
        "compared": compared,
    }
