"""Tests for FHIR Bundle parsing + reference resolution (Stage 1).

The parser is pure logic — it takes a FHIR Bundle dict and returns plain
record dataclasses with references resolved to the patient business key
(fhir_id). No database needed, so these run without Docker.
"""

from datetime import date

from medsync.pipeline.parser import parse_bundle


def _patient_entry(fhir_id: str, family: str = "Doe", given: str = "Jane") -> dict:
    return {
        "fullUrl": f"urn:uuid:{fhir_id}",
        "resource": {
            "resourceType": "Patient",
            "id": fhir_id,
            "name": [{"family": family, "given": [given]}],
            "gender": "female",
            "birthDate": "1980-01-01",
            "address": [
                {
                    "line": ["123 Main St"],
                    "city": "Springfield",
                    "state": "IL",
                    "postalCode": "62701",
                }
            ],
        },
    }


def _condition_entry(fhir_id: str, subject_ref: str, code: str = "44054006") -> dict:
    return {
        "fullUrl": f"urn:uuid:{fhir_id}",
        "resource": {
            "resourceType": "Condition",
            "id": fhir_id,
            "subject": {"reference": subject_ref},
            "clinicalStatus": {
                "coding": [{"code": "active"}]
            },
            "code": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": code,
                        "display": "Diabetes mellitus type 2",
                    }
                ]
            },
            "onsetDateTime": "2015-06-01T00:00:00Z",
        },
    }


def test_parses_patient_fields():
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [_patient_entry("pat-1")],
    }
    result = parse_bundle(bundle)
    assert len(result.patients) == 1
    p = result.patients[0]
    assert p.fhir_id == "pat-1"
    assert p.family_name == "Doe"
    assert p.given_name == "Jane"
    assert p.gender == "female"
    assert p.birth_date == date(1980, 1, 1)
    assert p.city == "Springfield"
    assert p.has_incomplete_data is False


def test_condition_resolves_to_patient_fhir_id_via_urn():
    """Synthea uses urn:uuid references; they must resolve to the patient fhir_id."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            _condition_entry("cond-1", subject_ref="urn:uuid:pat-1"),
        ],
    }
    result = parse_bundle(bundle)
    assert len(result.conditions) == 1
    c = result.conditions[0]
    assert c.fhir_id == "cond-1"
    assert c.patient_fhir_id == "pat-1"
    assert c.code == "44054006"
    assert c.system == "http://snomed.info/sct"
    assert c.clinical_status == "active"


def test_condition_resolves_to_patient_fhir_id_via_relative_ref():
    """Relative `Patient/{id}` references must also resolve."""
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            _patient_entry("pat-1"),
            _condition_entry("cond-1", subject_ref="Patient/pat-1"),
        ],
    }
    result = parse_bundle(bundle)
    assert result.conditions[0].patient_fhir_id == "pat-1"


def test_unresolvable_reference_is_flagged_not_dropped():
    """Missing-field policy: flag has_incomplete_data, keep the record, continue."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [_condition_entry("cond-1", subject_ref="urn:uuid:ghost")],
    }
    result = parse_bundle(bundle)
    assert len(result.conditions) == 1
    c = result.conditions[0]
    assert c.patient_fhir_id is None
    assert c.has_incomplete_data is True


def test_malformed_resource_is_skipped_not_crashing():
    """A resource that fails validation is logged + skipped; the bundle continues."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "ok", "gender": "male"}},
            {"resource": {"resourceType": "Patient", "gender": "not-a-valid-gender"}},
        ],
    }
    result = parse_bundle(bundle)
    # The valid one parses; the invalid one is recorded as an error, not a crash.
    assert any(p.fhir_id == "ok" for p in result.patients)
    assert result.error_count >= 1


def test_unhandled_resource_type_is_counted_as_skipped():
    """Increment 1 handles only Patient + Condition; others are deferred (Inc 2)."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            {"resource": {"resourceType": "Observation", "id": "obs-1", "status": "final",
                          "code": {"text": "hr"}}},
        ],
    }
    result = parse_bundle(bundle)
    assert result.skipped.get("Observation") == 1
