"""Stage 1 — FHIR Bundle parsing + reference resolution.  [MANUAL]

Takes a FHIR R4 Bundle (dict) and returns plain record dataclasses with
references resolved to business keys (patient/encounter ``fhir_id``).
Persistence is the Celery task's job — keeping this module pure makes it
unit-testable without a database.

Scope (CLAUDE.md §6.1, design spec): 8 core resource types get typed records;
5 deferred types (Immunization, CarePlan, CareTeam, Claim, Device) are stored
verbatim in ``raw_resources`` for Phase-4 promotion; anything else (Synthea
also emits Organization, Practitioner, …) is counted in ``skipped``.

Rules:
- Validate the 8 core types with the ``fhir.resources`` R4B Pydantic models.
- Never crash the bundle on a bad resource: log + record an error, continue.
- Never drop a record for a missing/unresolvable reference: flag
  ``has_incomplete_data`` and keep it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from fhir.resources.R4B.allergyintolerance import AllergyIntolerance as FHIRAllergy
from fhir.resources.R4B.condition import Condition as FHIRCondition
from fhir.resources.R4B.diagnosticreport import DiagnosticReport as FHIRDiagnosticReport
from fhir.resources.R4B.encounter import Encounter as FHIREncounter
from fhir.resources.R4B.medicationrequest import MedicationRequest as FHIRMedicationRequest
from fhir.resources.R4B.observation import Observation as FHIRObservation
from fhir.resources.R4B.patient import Patient as FHIRPatient
from fhir.resources.R4B.procedure import Procedure as FHIRProcedure

logger = logging.getLogger(__name__)

CORE_RESOURCE_TYPES = {
    "Patient",
    "Condition",
    "Encounter",
    "Observation",
    "MedicationRequest",
    "Procedure",
    "DiagnosticReport",
    "AllergyIntolerance",
}
DEFERRED_RESOURCE_TYPES = {"Immunization", "CarePlan", "CareTeam", "Claim", "Device"}
ALLOWED_RESOURCE_TYPES = CORE_RESOURCE_TYPES | DEFERRED_RESOURCE_TYPES


# --------------------------------------------------------------------------- #
# Record dataclasses
# --------------------------------------------------------------------------- #
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
class EncounterRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    status: str | None = None
    encounter_class: str | None = None
    type_code: str | None = None
    type_display: str | None = None
    reason_code: str | None = None
    reason_display: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    has_incomplete_data: bool = False


@dataclass
class ObservationRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    encounter_fhir_id: str | None = None
    code: str | None = None
    system: str | None = None
    display: str | None = None
    value_number: float | None = None
    value_unit: str | None = None
    value_string: str | None = None
    effective_date: datetime | None = None
    status: str | None = None
    has_incomplete_data: bool = False


@dataclass
class MedicationRequestRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    encounter_fhir_id: str | None = None
    code: str | None = None
    system: str | None = None
    display: str | None = None
    status: str | None = None
    authored_on: datetime | None = None
    has_incomplete_data: bool = False


@dataclass
class ProcedureRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    encounter_fhir_id: str | None = None
    code: str | None = None
    system: str | None = None
    display: str | None = None
    status: str | None = None
    performed_date: datetime | None = None
    has_incomplete_data: bool = False


@dataclass
class DiagnosticReportRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    encounter_fhir_id: str | None = None
    code: str | None = None
    system: str | None = None
    display: str | None = None
    status: str | None = None
    effective_date: datetime | None = None
    has_incomplete_data: bool = False


@dataclass
class AllergyRecord:
    fhir_id: str
    patient_fhir_id: str | None = None
    code: str | None = None
    system: str | None = None
    display: str | None = None
    clinical_status: str | None = None
    criticality: str | None = None
    has_incomplete_data: bool = False


@dataclass
class RawResourceRecord:
    fhir_id: str | None
    resource_type: str
    patient_fhir_id: str | None
    payload: dict


@dataclass
class ParseResult:
    patients: list[PatientRecord] = field(default_factory=list)
    conditions: list[ConditionRecord] = field(default_factory=list)
    encounters: list[EncounterRecord] = field(default_factory=list)
    observations: list[ObservationRecord] = field(default_factory=list)
    medication_requests: list[MedicationRequestRecord] = field(default_factory=list)
    procedures: list[ProcedureRecord] = field(default_factory=list)
    diagnostic_reports: list[DiagnosticReportRecord] = field(default_factory=list)
    allergies: list[AllergyRecord] = field(default_factory=list)
    raw_resources: list[RawResourceRecord] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    @property
    def typed_records(self) -> list:
        return [
            *self.patients,
            *self.conditions,
            *self.encounters,
            *self.observations,
            *self.medication_requests,
            *self.procedures,
            *self.diagnostic_reports,
            *self.allergies,
        ]

    @property
    def record_count(self) -> int:
        return len(self.typed_records) + len(self.raw_resources)

    @property
    def error_count(self) -> int:
        return len(self.errors)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _coerce_date(value) -> date | None:
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


def _coerce_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _coding(codeable) -> tuple[str | None, str | None, str | None]:
    """Return (code, system, display) from a CodeableConcept model, or (None,)*3."""
    if codeable and codeable.coding:
        c = codeable.coding[0]
        return c.code, c.system, c.display
    return None, None, None


def _reference_keys(entry: dict, resource: dict) -> list[str]:
    keys: list[str] = []
    if entry.get("fullUrl"):
        keys.append(entry["fullUrl"])
    rid = resource.get("id")
    rtype = resource.get("resourceType")
    if rid:
        keys.append(rid)
        if rtype:
            keys.append(f"{rtype}/{rid}")
    return keys


def _build_reference_index(entries: list[dict]) -> dict[str, tuple[str, str]]:
    """Map every reference form -> (resourceType, fhir_id) for all resources."""
    index: dict[str, tuple[str, str]] = {}
    for entry in entries:
        resource = entry.get("resource") or {}
        fhir_id = resource.get("id")
        rtype = resource.get("resourceType")
        if not fhir_id or not rtype:
            continue
        for key in _reference_keys(entry, resource):
            index[key] = (rtype, fhir_id)
    return index


def _resolve(ref_node, index: dict[str, tuple[str, str]], expected_type: str) -> str | None:
    """Resolve a Reference to a fhir_id, only if it points at expected_type."""
    if not ref_node or not getattr(ref_node, "reference", None):
        return None
    hit = index.get(ref_node.reference)
    if hit and hit[0] == expected_type:
        return hit[1]
    return None


def _patient_ref_from_payload(resource: dict, index: dict[str, tuple[str, str]]) -> str | None:
    """Best-effort patient resolution for deferred/raw resources, from the dict."""
    for key in ("subject", "patient"):
        node = resource.get(key) or {}
        ref = node.get("reference")
        if ref:
            hit = index.get(ref)
            if hit and hit[0] == "Patient":
                return hit[1]
    return None


# --------------------------------------------------------------------------- #
# Per-type parsers
# --------------------------------------------------------------------------- #
def _require_id(resource: dict, rtype: str) -> str:
    rid = resource.get("id")
    if not rid:
        raise ValueError(f"{rtype} resource missing required 'id' (cannot upsert)")
    return rid


def _parse_patient(resource: dict) -> PatientRecord:
    _require_id(resource, "Patient")
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
        a = model.address[0]
        if a.line:
            line = a.line[0]
        city, state, postal = a.city, a.state, a.postalCode

    birth = _coerce_date(model.birthDate)
    if birth is None:
        incomplete = True

    return PatientRecord(
        fhir_id=model.id, family_name=family, given_name=given, gender=model.gender,
        birth_date=birth, address_line=line, city=city, state=state, postal_code=postal,
        has_incomplete_data=incomplete,
    )


def _parse_condition(resource: dict, index) -> ConditionRecord:
    _require_id(resource, "Condition")
    model = FHIRCondition.model_validate(resource)
    pid = _resolve(model.subject, index, "Patient")
    code, system, display = _coding(model.code)
    status = _coding(model.clinicalStatus)[0]
    return ConditionRecord(
        fhir_id=model.id, patient_fhir_id=pid, code=code, system=system, display=display,
        clinical_status=status, onset_date=_coerce_date(getattr(model, "onsetDateTime", None)),
        has_incomplete_data=pid is None,
    )


def _parse_encounter(resource: dict, index) -> EncounterRecord:
    _require_id(resource, "Encounter")
    model = FHIREncounter.model_validate(resource)
    pid = _resolve(model.subject, index, "Patient")

    enc_class = None
    klass = getattr(model, "class_fhir", None)
    if klass is not None:
        enc_class = klass.code

    type_code = type_display = None
    if model.type:
        type_code, _, type_display = _coding(model.type[0])

    reason_code = reason_display = None
    if model.reasonCode:
        reason_code, _, reason_display = _coding(model.reasonCode[0])

    start = end = None
    if model.period:
        start = _coerce_datetime(model.period.start)
        end = _coerce_datetime(model.period.end)

    return EncounterRecord(
        fhir_id=model.id, patient_fhir_id=pid, status=model.status, encounter_class=enc_class,
        type_code=type_code, type_display=type_display, reason_code=reason_code,
        reason_display=reason_display, period_start=start, period_end=end,
        has_incomplete_data=pid is None,
    )


def _parse_observation(resource: dict, index) -> ObservationRecord:
    _require_id(resource, "Observation")
    model = FHIRObservation.model_validate(resource)
    pid = _resolve(model.subject, index, "Patient")
    eid = _resolve(model.encounter, index, "Encounter")
    code, system, display = _coding(model.code)

    value_number = value_unit = value_string = None
    if model.valueQuantity:
        value_number = float(model.valueQuantity.value) if model.valueQuantity.value is not None else None
        value_unit = model.valueQuantity.unit
    elif getattr(model, "valueString", None):
        value_string = model.valueString
    elif getattr(model, "valueCodeableConcept", None):
        value_string = _coding(model.valueCodeableConcept)[2]

    return ObservationRecord(
        fhir_id=model.id, patient_fhir_id=pid, encounter_fhir_id=eid, code=code, system=system,
        display=display, value_number=value_number, value_unit=value_unit, value_string=value_string,
        effective_date=_coerce_datetime(getattr(model, "effectiveDateTime", None)),
        status=model.status, has_incomplete_data=pid is None,
    )


def _parse_medication_request(resource: dict, index) -> MedicationRequestRecord:
    _require_id(resource, "MedicationRequest")
    model = FHIRMedicationRequest.model_validate(resource)
    pid = _resolve(model.subject, index, "Patient")
    eid = _resolve(model.encounter, index, "Encounter")
    code, system, display = _coding(getattr(model, "medicationCodeableConcept", None))
    return MedicationRequestRecord(
        fhir_id=model.id, patient_fhir_id=pid, encounter_fhir_id=eid, code=code, system=system,
        display=display, status=model.status,
        authored_on=_coerce_datetime(getattr(model, "authoredOn", None)),
        has_incomplete_data=pid is None,
    )


def _parse_procedure(resource: dict, index) -> ProcedureRecord:
    _require_id(resource, "Procedure")
    model = FHIRProcedure.model_validate(resource)
    pid = _resolve(model.subject, index, "Patient")
    eid = _resolve(model.encounter, index, "Encounter")
    code, system, display = _coding(model.code)
    return ProcedureRecord(
        fhir_id=model.id, patient_fhir_id=pid, encounter_fhir_id=eid, code=code, system=system,
        display=display, status=model.status,
        performed_date=_coerce_datetime(getattr(model, "performedDateTime", None)),
        has_incomplete_data=pid is None,
    )


def _parse_diagnostic_report(resource: dict, index) -> DiagnosticReportRecord:
    _require_id(resource, "DiagnosticReport")
    model = FHIRDiagnosticReport.model_validate(resource)
    pid = _resolve(model.subject, index, "Patient")
    eid = _resolve(model.encounter, index, "Encounter")
    code, system, display = _coding(model.code)
    return DiagnosticReportRecord(
        fhir_id=model.id, patient_fhir_id=pid, encounter_fhir_id=eid, code=code, system=system,
        display=display, status=model.status,
        effective_date=_coerce_datetime(getattr(model, "effectiveDateTime", None)),
        has_incomplete_data=pid is None,
    )


def _parse_allergy(resource: dict, index) -> AllergyRecord:
    _require_id(resource, "AllergyIntolerance")
    model = FHIRAllergy.model_validate(resource)
    pid = _resolve(model.patient, index, "Patient")
    code, system, display = _coding(model.code)
    status = _coding(model.clinicalStatus)[0]
    return AllergyRecord(
        fhir_id=model.id, patient_fhir_id=pid, code=code, system=system, display=display,
        clinical_status=status, criticality=model.criticality, has_incomplete_data=pid is None,
    )


_CORE_DISPATCH = {
    "Condition": (_parse_condition, "conditions"),
    "Encounter": (_parse_encounter, "encounters"),
    "Observation": (_parse_observation, "observations"),
    "MedicationRequest": (_parse_medication_request, "medication_requests"),
    "Procedure": (_parse_procedure, "procedures"),
    "DiagnosticReport": (_parse_diagnostic_report, "diagnostic_reports"),
    "AllergyIntolerance": (_parse_allergy, "allergies"),
}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def parse_bundle(bundle: dict) -> ParseResult:
    """Parse a FHIR Bundle dict into resolved record dataclasses."""
    result = ParseResult()
    entries = bundle.get("entry") or []
    index = _build_reference_index(entries)

    for entry in entries:
        resource = entry.get("resource") or {}
        rtype = resource.get("resourceType")
        if rtype is None:
            result.errors.append({"resource_type": None, "error": "missing resourceType"})
            continue

        # Out-of-scope types (Organization, Practitioner, …): count + continue.
        if rtype not in ALLOWED_RESOURCE_TYPES:
            result.skipped[rtype] = result.skipped.get(rtype, 0) + 1
            continue

        try:
            if rtype == "Patient":
                result.patients.append(_parse_patient(resource))
            elif rtype in _CORE_DISPATCH:
                parser_fn, attr = _CORE_DISPATCH[rtype]
                getattr(result, attr).append(parser_fn(resource, index))
            else:  # deferred type → store verbatim for Phase-4 promotion
                result.raw_resources.append(
                    RawResourceRecord(
                        fhir_id=resource.get("id"),
                        resource_type=rtype,
                        patient_fhir_id=_patient_ref_from_payload(resource, index),
                        payload=resource,
                    )
                )
        except Exception as exc:  # validation/shape error — log + record, never crash
            logger.warning("skip %s %s: %s", rtype, resource.get("id"), exc)
            result.errors.append(
                {"resource_type": rtype, "fhir_id": resource.get("id"), "error": str(exc)}
            )

    return result
