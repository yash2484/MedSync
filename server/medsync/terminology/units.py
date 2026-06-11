"""Unit conversions for lab/vital normalization (CLAUDE.md §6.2).

Converts US conventional units to SI:
- Temperature °F → °C
- Glucose mg/dL → mmol/L (factor 0.0555)
- Cholesterol (total/HDL/LDL) mg/dL → mmol/L (factor 0.02586)
- Triglyceride mg/dL → mmol/L (factor 0.01129)

The conversion factor for mass→molar units is analyte-specific, so it is keyed
off the observation's LOINC code.
"""

from __future__ import annotations

GLUCOSE_LOINCS = {"2339-0", "2345-7", "1558-6", "1547-9"}
CHOLESTEROL_LOINCS = {"2093-3", "2085-9", "2089-1", "13457-7"}
TRIGLYCERIDE_LOINCS = {"2571-8"}

_GLUCOSE_FACTOR = 0.0555
_CHOLESTEROL_FACTOR = 0.02586
_TRIGLYCERIDE_FACTOR = 0.01129


def fahrenheit_to_celsius(f: float) -> float:
    return round((f - 32.0) * 5.0 / 9.0, 2)


def celsius_to_fahrenheit(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 2)


def mg_dl_to_mmol_l(value: float, factor: float) -> float:
    return round(value * factor, 3)


def to_si(loinc_code: str | None, value: float | None, unit: str | None) -> tuple[float, str] | None:
    """Return (value_si, unit_si) if a conversion applies, else None.

    None means "already SI or not convertible" — the caller keeps the original.
    """
    if value is None:
        return None
    u = (unit or "").lower().replace(" ", "")

    # Temperature: °F -> °C (LOINC 8310-5 body temperature)
    if loinc_code == "8310-5" and u in {"[degf]", "degf", "f", "°f"}:
        return fahrenheit_to_celsius(value), "Cel"

    if u in {"mg/dl", "mg/dl."}:
        if loinc_code in GLUCOSE_LOINCS:
            return mg_dl_to_mmol_l(value, _GLUCOSE_FACTOR), "mmol/L"
        if loinc_code in CHOLESTEROL_LOINCS:
            return mg_dl_to_mmol_l(value, _CHOLESTEROL_FACTOR), "mmol/L"
        if loinc_code in TRIGLYCERIDE_LOINCS:
            return mg_dl_to_mmol_l(value, _TRIGLYCERIDE_FACTOR), "mmol/L"

    return None
