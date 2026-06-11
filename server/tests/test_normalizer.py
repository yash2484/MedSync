"""Tests for Stage 2 terminology normalization (crosswalk + units)."""

import json
from pathlib import Path

from medsync.pipeline.normalizer import normalize_condition, normalize_observation
from medsync.pipeline.parser import parse_bundle
from medsync.terminology.crosswalk import get_crosswalk
from medsync.terminology.units import fahrenheit_to_celsius, mg_dl_to_mmol_l, to_si

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthea"


def test_crosswalk_loads_curated_sets():
    cw = get_crosswalk()
    assert cw.condition_count >= 40
    assert cw.loinc_count >= 20


def test_snomed_diabetes_maps_to_icd10_e11():
    cw = get_crosswalk()
    m = cw.lookup_condition("44054006", "http://snomed.info/sct")
    assert m is not None
    assert m.icd10_code == "E11.9"
    assert m.mapping_confidence > 0.0


def test_icd10_reverse_lookup_resolves_snomed():
    cw = get_crosswalk()
    m = cw.lookup_condition("I10", "http://hl7.org/fhir/sid/icd-10-cm")
    assert m is not None
    assert m.icd10_code == "I10"


def test_unmapped_condition_flags_failure_and_keeps_provenance():
    cw = get_crosswalk()
    n = normalize_condition("0000000", "http://snomed.info/sct", cw)
    assert n.normalization_failed is True
    assert n.snomed_code == "0000000"  # provenance preserved
    assert n.icd10_code is None


def test_fahrenheit_to_celsius():
    assert fahrenheit_to_celsius(98.6) == 37.0


def test_mg_dl_to_mmol_l_glucose():
    assert mg_dl_to_mmol_l(180, 0.0555) == 9.99


def test_to_si_converts_glucose_mg_dl():
    result = to_si("2339-0", 180, "mg/dL")
    assert result == (9.99, "mmol/L")


def test_to_si_returns_none_for_already_si_unit():
    # Heart rate /min is not convertible — keep original.
    assert to_si("8867-4", 112, "beats/min") is None


def test_normalize_observation_standardizes_loinc():
    cw = get_crosswalk()
    n = normalize_observation("8867-4", "http://loinc.org", 112, "beats/min", cw)
    assert n.loinc_code == "8867-4"
    assert n.canonical_display.startswith("Heart rate")
    assert n.normalization_failed is False


def test_diabetes_patient_has_both_icd10_and_snomed():
    """CLINICAL ASSERTION: a Synthea diabetes condition resolves to BOTH a
    SNOMED concept (44054006) and an ICD-10 code (E11.x)."""
    bundle = json.loads((FIXTURES / "fixture_diabetes_patient.json").read_text())
    result = parse_bundle(bundle)
    cw = get_crosswalk()

    diabetes = next(c for c in result.conditions if c.code == "44054006")
    n = normalize_condition(diabetes.code, diabetes.system, cw)

    assert n.snomed_code == "44054006"
    assert n.icd10_code.startswith("E11")
    assert not n.normalization_failed
