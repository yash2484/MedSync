# server/tests/test_enricher.py
from datetime import datetime
from types import SimpleNamespace

from medsync.pipeline.enricher import compute_summary


def test_compute_summary_counts_and_active_conditions():
    conditions = [
        SimpleNamespace(display="Diabetes", icd10_code="E11.9", clinical_status="active"),
        SimpleNamespace(display="Old fracture", icd10_code="S00", clinical_status="resolved"),
    ]
    meds = [SimpleNamespace(fhir_id="m1"), SimpleNamespace(fhir_id="m2")]
    encs = [
        SimpleNamespace(period_start=datetime(2020, 1, 1)),
        SimpleNamespace(period_start=datetime(2023, 5, 1)),
    ]
    s = compute_summary(conditions, meds, encs)
    assert s["condition_count"] == 2
    assert s["active_condition_count"] == 1
    assert s["active_conditions"] == ["Diabetes"]
    assert s["medication_count"] == 2
    assert s["encounter_count"] == 2
    assert s["last_encounter_date"] == "2023-05-01"


def test_compute_summary_handles_empty():
    s = compute_summary([], [], [])
    assert s["condition_count"] == 0
    assert s["last_encounter_date"] is None
