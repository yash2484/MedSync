"""Tests for FHIR Bundle parsing + reference resolution (Stage 1).

The parser is pure logic — it takes a FHIR Bundle dict and returns plain
record dataclasses with references resolved to the patient business key
(fhir_id). No database needed, so these run without Docker.
"""

import json
from datetime import date
from pathlib import Path

from medsync.pipeline.parser import parse_bundle

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthea"


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


def test_out_of_scope_resource_type_is_counted_as_skipped():
    """Synthea also emits Organization/Practitioner/etc. — counted, not errored."""
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            {"resource": {"resourceType": "Organization", "id": "org-1", "name": "Acme Health"}},
        ],
    }
    result = parse_bundle(bundle)
    assert result.skipped.get("Organization") == 1
    assert result.error_count == 0


def test_encounter_parses_and_resolves_patient():
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            {
                "fullUrl": "urn:uuid:enc-1",
                "resource": {
                    "resourceType": "Encounter",
                    "id": "enc-1",
                    "status": "finished",
                    "class": {"system": "x", "code": "EMER", "display": "emergency"},
                    "subject": {"reference": "urn:uuid:pat-1"},
                    "reasonCode": [{"coding": [{"system": "snomed", "code": "29857009",
                                                "display": "Chest pain"}]}],
                    "period": {"start": "2021-03-01T08:00:00Z", "end": "2021-03-01T10:00:00Z"},
                },
            },
        ],
    }
    result = parse_bundle(bundle)
    assert len(result.encounters) == 1
    e = result.encounters[0]
    assert e.patient_fhir_id == "pat-1"
    assert e.encounter_class == "EMER"
    assert e.reason_code == "29857009"
    assert e.reason_display == "Chest pain"
    assert e.period_start is not None


def test_observation_resolves_patient_and_encounter():
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            {
                "fullUrl": "urn:uuid:enc-1",
                "resource": {
                    "resourceType": "Encounter", "id": "enc-1", "status": "finished",
                    "class": {"code": "AMB"}, "subject": {"reference": "urn:uuid:pat-1"},
                },
            },
            {
                "fullUrl": "urn:uuid:obs-1",
                "resource": {
                    "resourceType": "Observation", "id": "obs-1", "status": "final",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4",
                                         "display": "Heart rate"}]},
                    "subject": {"reference": "urn:uuid:pat-1"},
                    "encounter": {"reference": "urn:uuid:enc-1"},
                    "valueQuantity": {"value": 112, "unit": "beats/min"},
                    "effectiveDateTime": "2021-03-01T08:30:00Z",
                },
            },
        ],
    }
    result = parse_bundle(bundle)
    assert len(result.observations) == 1
    o = result.observations[0]
    assert o.patient_fhir_id == "pat-1"
    assert o.encounter_fhir_id == "enc-1"
    assert o.code == "8867-4"
    assert o.value_number == 112.0
    assert o.value_unit == "beats/min"


def test_deferred_type_goes_to_raw_resources():
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            {
                "resource": {
                    "resourceType": "Immunization", "id": "imm-1", "status": "completed",
                    "patient": {"reference": "urn:uuid:pat-1"},
                    "vaccineCode": {"text": "Influenza"},
                    "occurrenceDateTime": "2022-10-01",
                }
            },
        ],
    }
    result = parse_bundle(bundle)
    assert len(result.raw_resources) == 1
    raw = result.raw_resources[0]
    assert raw.resource_type == "Immunization"
    assert raw.fhir_id == "imm-1"
    assert raw.patient_fhir_id == "pat-1"
    assert raw.payload["status"] == "completed"


def test_mixed_bundle_counts_all_record_categories():
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            _patient_entry("pat-1"),
            _condition_entry("cond-1", "urn:uuid:pat-1"),
            {"resource": {"resourceType": "AllergyIntolerance", "id": "alg-1",
                          "patient": {"reference": "urn:uuid:pat-1"},
                          "clinicalStatus": {"coding": [{"code": "active"}]},
                          "criticality": "high",
                          "code": {"coding": [{"system": "rxnorm", "code": "7980",
                                               "display": "Penicillin"}]}}},
            {"resource": {"resourceType": "Device", "id": "dev-1",
                          "patient": {"reference": "urn:uuid:pat-1"}}},
        ],
    }
    result = parse_bundle(bundle)
    assert len(result.patients) == 1
    assert len(result.conditions) == 1
    assert len(result.allergies) == 1
    assert result.allergies[0].criticality == "high"
    assert len(result.raw_resources) == 1  # Device deferred
    assert result.record_count == 4
    assert result.error_count == 0


def test_all_types_fixture_parses_without_errors():
    """The 13-type fixture must parse with zero crashes (Phase 1 done-criterion)."""
    bundle = json.loads((FIXTURES / "fixture_all_types.json").read_text())
    r = parse_bundle(bundle)

    assert r.error_count == 0, r.errors
    assert len(r.patients) == 1
    assert len(r.encounters) == 1
    assert len(r.conditions) == 1
    assert len(r.observations) == 1
    assert len(r.medication_requests) == 1
    assert len(r.procedures) == 1
    assert len(r.diagnostic_reports) == 1
    assert len(r.allergies) == 1
    # 5 deferred types -> raw_resources
    assert len(r.raw_resources) == 5
    assert {raw.resource_type for raw in r.raw_resources} == {
        "Immunization", "CarePlan", "CareTeam", "Claim", "Device"
    }
    # out-of-scope Organization -> skipped, not error
    assert r.skipped.get("Organization") == 1
    # cross-resource references resolved
    assert r.observations[0].encounter_fhir_id == "enc-3333"
    assert r.medication_requests[0].code == "243670"
