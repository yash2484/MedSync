"""ICD-10 ↔ SNOMED CT crosswalk + LOINC normalization tables.  [MANUAL]

Design (CLAUDE.md §6.2): ICD-10 ↔ SNOMED is one-to-many; we keep a curated
subset and preserve provenance (original code/system + mapping confidence +
source). Lossy mapping with provenance beats requiring perfect 1:1 equivalence
— data must flow; what we can't map gets flagged, not dropped.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "terminology"
CROSSWALK_CSV = DATA_DIR / "icd10_snomed_crosswalk.csv"
LOINC_CSV = DATA_DIR / "loinc_normalized.csv"

SNOMED_SYSTEM = "http://snomed.info/sct"
ICD10_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
LOINC_SYSTEM = "http://loinc.org"


def system_kind(system: str | None) -> str | None:
    """Classify a coding system URI as 'snomed', 'icd10', 'loinc', or None."""
    if not system:
        return None
    s = system.lower()
    if "snomed" in s:
        return "snomed"
    if "icd-10" in s or "icd10" in s:
        return "icd10"
    if "loinc" in s:
        return "loinc"
    return None


@dataclass(frozen=True)
class ConditionMapping:
    snomed_code: str
    snomed_display: str
    icd10_code: str
    icd10_display: str
    mapping_confidence: float
    mapping_source: str


@dataclass(frozen=True)
class LoincEntry:
    loinc_code: str
    long_common_name: str
    standard_unit: str
    category: str


class Crosswalk:
    """In-memory ICD-10↔SNOMED crosswalk with lookup by either code."""

    def __init__(self, mappings: list[ConditionMapping], loinc: dict[str, LoincEntry]):
        self._by_snomed = {m.snomed_code: m for m in mappings}
        self._by_icd10 = {m.icd10_code: m for m in mappings}
        self._loinc = loinc

    @classmethod
    def load(cls, crosswalk_csv: Path = CROSSWALK_CSV, loinc_csv: Path = LOINC_CSV) -> Crosswalk:
        mappings: list[ConditionMapping] = []
        with crosswalk_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                mappings.append(
                    ConditionMapping(
                        snomed_code=row["snomed_code"].strip(),
                        snomed_display=row["snomed_display"].strip(),
                        icd10_code=row["icd10_code"].strip(),
                        icd10_display=row["icd10_display"].strip(),
                        mapping_confidence=float(row["mapping_confidence"]),
                        mapping_source=row["mapping_source"].strip(),
                    )
                )
        loinc: dict[str, LoincEntry] = {}
        with loinc_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                entry = LoincEntry(
                    loinc_code=row["loinc_code"].strip(),
                    long_common_name=row["long_common_name"].strip(),
                    standard_unit=row["standard_unit"].strip(),
                    category=row["category"].strip(),
                )
                loinc[entry.loinc_code] = entry
        return cls(mappings, loinc)

    def lookup_condition(self, code: str | None, system: str | None) -> ConditionMapping | None:
        """Resolve a condition code (SNOMED or ICD-10) to its crosswalk row."""
        if not code:
            return None
        kind = system_kind(system)
        if kind == "snomed":
            return self._by_snomed.get(code)
        if kind == "icd10":
            return self._by_icd10.get(code)
        # Unknown system: try both sides (SNOMED codes are numeric, ICD-10 alpha-num).
        return self._by_snomed.get(code) or self._by_icd10.get(code)

    def lookup_loinc(self, code: str | None) -> LoincEntry | None:
        if not code:
            return None
        return self._loinc.get(code)

    @property
    def condition_count(self) -> int:
        return len(self._by_snomed)

    @property
    def loinc_count(self) -> int:
        return len(self._loinc)


@lru_cache
def get_crosswalk() -> Crosswalk:
    """Process-wide singleton (CSV is small; load once)."""
    return Crosswalk.load()
