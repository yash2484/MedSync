"""Stage 2 — terminology normalization.  [MANUAL]

Pure functions (``normalize_condition`` / ``normalize_observation``) resolve a
code to its canonical cross-terminology representation and are unit-testable
without a database. ``normalize_records`` is the DB sweep the Celery stage runs.

Policy (CLAUDE.md §6.2, §9.1): preserve the original code/system as provenance
(already stored on the row), fill the canonical counterpart codes, and flag —
never drop — anything we can't map (``normalization_failed=True``).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medsync.models.database import Condition, Observation
from medsync.terminology.crosswalk import Crosswalk, get_crosswalk, system_kind
from medsync.terminology.units import to_si


@dataclass
class NormalizedCondition:
    snomed_code: str | None
    icd10_code: str | None
    mapping_confidence: float | None
    mapping_source: str | None
    normalization_failed: bool


@dataclass
class NormalizedObservation:
    loinc_code: str | None
    canonical_display: str | None
    value_canonical: float | None
    value_canonical_unit: str | None
    normalization_failed: bool


def normalize_condition(code: str | None, system: str | None, crosswalk: Crosswalk) -> NormalizedCondition:
    mapping = crosswalk.lookup_condition(code, system)
    if mapping is not None:
        return NormalizedCondition(
            snomed_code=mapping.snomed_code,
            icd10_code=mapping.icd10_code,
            mapping_confidence=mapping.mapping_confidence,
            mapping_source=mapping.mapping_source,
            normalization_failed=False,
        )
    # Unmapped: keep the side we know for provenance, flag the failure.
    kind = system_kind(system)
    return NormalizedCondition(
        snomed_code=code if kind == "snomed" else None,
        icd10_code=code if kind == "icd10" else None,
        mapping_confidence=None,
        mapping_source=None,
        normalization_failed=True,
    )


def normalize_observation(
    code: str | None, system: str | None, value_number: float | None,
    value_unit: str | None, crosswalk: Crosswalk,
) -> NormalizedObservation:
    loinc_code = code if system_kind(system) == "loinc" else None
    entry = crosswalk.lookup_loinc(loinc_code) if loinc_code else None
    si = to_si(loinc_code, value_number, value_unit)
    value_canonical, value_canonical_unit = si if si else (None, None)
    return NormalizedObservation(
        loinc_code=loinc_code,
        canonical_display=entry.long_common_name if entry else None,
        value_canonical=value_canonical,
        value_canonical_unit=value_canonical_unit,
        normalization_failed=entry is None,
    )


async def normalize_records(session: AsyncSession) -> dict:
    """Normalize every not-yet-normalized condition + observation. Idempotent."""
    crosswalk = get_crosswalk()
    stats = {
        "conditions_normalized": 0, "conditions_failed": 0,
        "observations_normalized": 0, "observations_failed": 0,
    }

    conditions = (
        await session.execute(select(Condition).where(Condition.normalized.is_(False)))
    ).scalars().all()
    for c in conditions:
        norm = normalize_condition(c.code, c.system, crosswalk)
        c.snomed_code = norm.snomed_code
        c.icd10_code = norm.icd10_code
        c.mapping_confidence = norm.mapping_confidence
        c.mapping_source = norm.mapping_source
        c.normalization_failed = norm.normalization_failed
        c.normalized = True
        # Invariant (CLAUDE.md §9.2): mapped (both codes) OR flagged failed.
        assert (c.snomed_code and c.icd10_code) or c.normalization_failed
        stats["conditions_failed" if norm.normalization_failed else "conditions_normalized"] += 1

    observations = (
        await session.execute(select(Observation).where(Observation.normalized.is_(False)))
    ).scalars().all()
    for o in observations:
        norm = normalize_observation(o.code, o.system, o.value_number, o.value_unit, crosswalk)
        o.loinc_code = norm.loinc_code
        o.canonical_display = norm.canonical_display
        o.value_canonical = norm.value_canonical
        o.value_canonical_unit = norm.value_canonical_unit
        o.normalization_failed = norm.normalization_failed
        o.normalized = True
        stats["observations_failed" if norm.normalization_failed else "observations_normalized"] += 1

    await session.commit()
    return stats
