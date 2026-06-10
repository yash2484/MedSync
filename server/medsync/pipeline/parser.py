"""Stage 1 — FHIR Bundle parsing + reference resolution.  [MANUAL]

Takes a FHIR R4 Bundle (as a dict) and returns plain record dataclasses with
references resolved to the patient business key (``fhir_id``). Persistence is
the Celery task's job — keeping this module pure makes it unit-testable
without a database.

Design rules (CLAUDE.md §6.1, §9.1):
- Validate each resource with the ``fhir.resources`` R4B Pydantic models.
- Never crash the bundle on a bad resource: log it as an error and continue.
- Never drop a record for a missing/unresolvable reference: flag
  ``has_incomplete_data`` and keep it.

Increment 1 handles Patient + Condition. Other resource types are counted in
``skipped`` and handled in Increment 2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from fhir.resources.R4B.condition import Condition as FHIRCondition
from fhir.resources.R4B.patient import Patient as FHIRPatient

logger = logging.getLogger(__name__)

HANDLED_RESOURCE_TYPES = {"Patient", "Condition"}


@dataclass
class PatientRecord:
    fhir_id: str
    family_name: str | None = None
    given_name: str | None = None
    gender: str | None = None
    birth_date: date | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    has_incomplete_data: bool = False


@dataclass
class ConditionRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    code: str | None = None
    system: str | None = None
    display: str | None = None
    clinical_status: str | None = None
    onset_date: date | None = None
    has_incomplete_data: bool = False


@dataclass
class ParseResult:
    patients: list[PatientRecord] = field(default_factory=list)
    conditions: list[ConditionRecord] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return len(self.patients) + len(self.conditions)

    @property
    def error_count(self) -> int:
        return len(self.errors)


def _coerce_date(value) -> date | None:
    """FHIR dates may be date, datetime, or ISO string. Return a date or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _reference_keys(entry: dict, resource: dict) -> list[str]:
    """All keys a later reference might use to point at this resource."""
    keys: list[str] = []
    full_url = entry.get("fullUrl")
    if full_url:
        keys.append(full_url)
    rid = resource.get("id")
    rtype = resource.get("resourceType")
    if rid:
        keys.append(rid)
        if rtype:
            keys.append(f"{rtype}/{rid}")
    return keys


def _build_patient_index(entries: list[dict]) -> dict[str, str]:
    """Map every reference form (urn:uuid, Patient/{id}, bare id) -> patient fhir_id."""
    index: dict[str, str] = {}
    for entry in entries:
        resource = entry.get("resource") or {}
        if resource.get("resourceType") != "Patient":
            continue
        fhir_id = resource.get("id")
        if not fhir_id:
            continue
        for key in _reference_keys(entry, resource):
            index[key] = fhir_id
    return index


def _parse_patient(resource: dict) -> PatientRecord:
    if not resource.get("id"):
        raise ValueError("Patient resource missing required 'id' (cannot upsert)")
    model = FHIRPatient.model_validate(resource)
    incomplete = False

    family = given = None
    if model.name:
        family = model.name[0].family
        if model.name[0].given:
            given = model.name[0].given[0]
    if not family:
        incomplete = True

    line = city = state = postal = None
    if model.address:
        addr = model.address[0]
        if addr.line:
            line = addr.line[0]
        city, state, postal = addr.city, addr.state, addr.postalCode

    birth = _coerce_date(model.birthDate)
    if birth is None:
        incomplete = True

    return PatientRecord(
        fhir_id=model.id,
        family_name=family,
        given_name=given,
        gender=model.gender,
        birth_date=birth,
        address_line=line,
        city=city,
        state=state,
        postal_code=postal,
        has_incomplete_data=incomplete,
    )


def _parse_condition(resource: dict, patient_index: dict[str, str]) -> ConditionRecord:
    if not resource.get("id"):
        raise ValueError("Condition resource missing required 'id' (cannot upsert)")
    model = FHIRCondition.model_validate(resource)
    incomplete = False

    patient_fhir_id = None
    if model.subject and model.subject.reference:
        patient_fhir_id = patient_index.get(model.subject.reference)
    if patient_fhir_id is None:
        incomplete = True

    code = system = display = None
    if model.code and model.code.coding:
        coding = model.code.coding[0]
        code, system, display = coding.code, coding.system, coding.display

    clinical_status = None
    if model.clinicalStatus and model.clinicalStatus.coding:
        clinical_status = model.clinicalStatus.coding[0].code

    onset = _coerce_date(getattr(model, "onsetDateTime", None))

    return ConditionRecord(
        fhir_id=model.id,
        patient_fhir_id=patient_fhir_id,
        code=code,
        system=system,
        display=display,
        clinical_status=clinical_status,
        onset_date=onset,
        has_incomplete_data=incomplete,
    )


def parse_bundle(bundle: dict) -> ParseResult:
    """Parse a FHIR Bundle dict into resolved record dataclasses."""
    result = ParseResult()
    entries = bundle.get("entry") or []
    patient_index = _build_patient_index(entries)

    for entry in entries:
        resource = entry.get("resource") or {}
        rtype = resource.get("resourceType")
        if rtype is None:
            result.errors.append({"resource_type": None, "error": "missing resourceType"})
            continue

        if rtype not in HANDLED_RESOURCE_TYPES:
            result.skipped[rtype] = result.skipped.get(rtype, 0) + 1
            continue

        try:
            if rtype == "Patient":
                result.patients.append(_parse_patient(resource))
            elif rtype == "Condition":
                result.conditions.append(_parse_condition(resource, patient_index))
        except Exception as exc:  # validation or shape error — log + skip, never crash
            logger.warning("skip %s %s: %s", rtype, resource.get("id"), exc)
            result.errors.append(
                {"resource_type": rtype, "fhir_id": resource.get("id"), "error": str(exc)}
            )

    return result
