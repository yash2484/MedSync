# MedSync Phase 1 — FHIR Pipeline Core: Design Spec

**Date:** 2026-06-10
**Status:** Approved
**Reference:** `Medsync.md` (full spec), `CLAUDE.md` (build guide), §10 Phase 1 done-criteria
**Build window:** Days 1–10 of the 4–5 week plan

---

## Context

MedSync is a FHIR-native clinical data pipeline with a hybrid AI triage engine, built as a
portfolio project to signal health-tech + AI engineering depth. Phase 1 builds the foundation
everything else sits on: an async pipeline that ingests a FHIR R4 Bundle, parses + validates it,
normalizes terminology across ICD-10/SNOMED/LOINC, deduplicates patient identities, enriches, and
stores — with real-time pipeline status over WebSocket.

The backend is where the hiring signal lives. Phase 1 must be deep and correct; the frontend in
Phase 1 is minimal (upload + status only).

---

## Settled Decisions (from brainstorming, 2026-06-10)

| Decision | Choice | Rationale |
|---|---|---|
| Synthea test data | Claude generates 8–10 hand-crafted FHIR R4 dev fixtures now | Unblocks all Phase 1 work without a 2GB download; full set added later for benchmarks |
| Terminology crosswalk | Claude curates top-200 ICD-10↔SNOMED + top-100 LOINC CSVs | No UMLS license needed; covers Synthea common conditions |
| Python tooling | `uv` (user installs) | Fastest resolver, pyproject-native, good Docker layer caching |
| Build sequencing | Vertical slice first | De-risks async integration early before broadening |

---

## Scope Reconciliation (spec contradiction resolved)

The spec conflicts on resource-type count: Phase 1 "Done when" requires *"all 13 resource types
parse without exception,"* while Anti-Patterns says *"Don't add more than 8 core FHIR resource
types in Phase 1."*

**Resolution:** Parse and validate **all 13** types via `fhir.resources` (parsing is cheap). Give
only the **8 core** types full relational models + normalization:
`Patient, Condition, Observation, Encounter, MedicationRequest, Procedure, DiagnosticReport,
AllergyIntolerance`. The remaining 5 (`Immunization, CarePlan, CareTeam, Claim, Device`) are
validated and persisted as raw JSONB in a `raw_resources` table, to be promoted to relational
models in Phase 4 if time allows. This satisfies both rules.

---

## Architecture (Phase 1 subset)

### Service topology (`docker-compose.yml`)
- `api` — FastAPI, port 8000
- `worker` — Celery worker (shares the api image)
- `postgres` — PostgreSQL 16, port 5432
- `redis` — Redis 7, port 6379 (Celery broker + status cache + WebSocket pub/sub)
- ChromaDB **deferred to Phase 2** (only needed for RAG)

### Pipeline (Celery chain)
```
POST /api/v1/bundles/upload
   → create pipeline_runs row (status=pending)
   → Celery chain: parse.s(run_id) | normalize.s() | deduplicate.s() | enrich.s()
        each stage: update pipeline_runs {stage, status, record_count, error_count}
                    Redis PUBLISH pipeline:{run_id}
   → FastAPI WebSocket SUBSCRIBE → frontend PipelineStatus
```
(Triage stage is appended in Phase 2.)

### Data flow
FHIR Bundle JSON → parse + reference resolution (refs → FK) → normalize codes + units →
dedup (cluster_id) → enrich (summary + timeline) → PostgreSQL.

---

## Data Model (Phase 1 tables)

- `pipeline_runs` — one row per upload; per-stage status tracking
- `patients`, `encounters`, `observations`, `conditions`, `medication_requests`,
  `procedures`, `diagnostic_reports`, `allergy_intolerances` — 8 core relational
- `raw_resources` — JSONB store for the 5 deferred resource types
- `patient_links` — dedup clusters (patient_id, cluster_id, match_zone, score)

Audit/auth tables and PHI field-encryption land in Phase 3.

**Invariants (CLAUDE.md §9.4):** idempotent upserts on `fhir_id` (`ON CONFLICT DO UPDATE`);
soft deletes only (`deleted_at`); every stage updates `pipeline_runs`.

---

## Build Increments (vertical slice)

### Increment 0 — Scaffolding
git init; monorepo (`server/` + `client/`); `uv` `pyproject.toml`; `docker-compose.yml` (4
services); `config.py` (Pydantic BaseSettings); async SQLAlchemy session; Alembic init; `/health`.
**Done:** `docker compose up` boots all 4 services; `GET /health` → 200.

### Increment 1 — The spine (Patient + Condition only)
Upload endpoint → `pipeline_runs` → Celery `parse` → `fhir.resources` parse →
resolve `Condition.subject → Patient` FK → idempotent upsert → `GET /patients`, `GET /patients/{id}`
→ WebSocket status streaming.
**Done:** upload a 2-patient fixture, see patients + conditions via API, watch stage transitions live.

### Increment 2 — Full parser
All 13 types parsed; full reference resolution (`Observation.encounter → Encounter`, etc.);
missing-field flagging (`has_incomplete_data=True`, never reject).
**Done:** a fixture exercising all 13 types parses with zero crashes; deferred types in `raw_resources`.

### Increment 3 — Stage 2 Normalize
Curated crosswalk CSVs loaded; ICD-10↔SNOMED mapping with provenance
(`{canonical_code, canonical_system, original_code, original_system, mapping_confidence,
mapping_source}`); LOINC normalization; unit conversion; `normalization_failed` flag for unmapped.
**Done:** diabetes fixture has ICD-10 E11.x AND SNOMED 44054006; unmapped codes flagged, not dropped.

### Increment 4 — Stage 3 Dedup + Stage 4 Enrich
Fellegi-Sunter via `recordlinkage`: Soundex(last_name)+birth_year blocking; Jaro-Winkler (name),
exact (DOB), token-overlap (address) scorers; 3 zones (match/possible/non-match); `cluster_id`
assignment; possible-match → flag, never auto-merge. Enrich: patient summary (active conditions,
meds) + chronological clinical timeline.
**Done:** same patient (slight name variation) in two bundles → single cluster_id + possible-match flag.

### Increment 5 — Phase 1 hardening
Section 9.2 validation checkpoints as assertions; the 2 Phase-1 clinical assertion tests; README
benchmark stub.
**Done:** all Phase 1 "Done when" criteria (CLAUDE.md §10) met; tests green.

---

## Error Handling & Self-Healing (CLAUDE.md §9)

| Stage | On failure | Never |
|---|---|---|
| Parse | log `{resource_type, fhir_id, error}`, skip resource, continue | crash the bundle |
| Normalize | store original code, set `normalization_failed=True`, continue | block on unmapped codes |
| Deduplicate | log record_id, skip, continue | auto-merge possible-matches |
| Enrich | log, store partial summary, continue | block on missing conditions |

Validation assertions inserted at each stage boundary (resource_type ∈ allowed set; canonical_code
not null OR normalization_failed; no patient_id in two distinct cluster_ids).

---

## Testing

- `pytest` + `pytest-asyncio` + `httpx`; real test PostgreSQL (Docker `test` profile / fixture).
- No DB mocking for integration tests.
- Phase 1 clinical assertion tests:
  - `test_diabetes_patient_has_both_icd10_and_snomed`
  - `test_same_patient_in_two_bundles_produces_single_linked_record`

---

## Out of Scope for Phase 1 (forecast)

- AI triage engine, LangGraph, RAG, ChromaDB → Phase 2
- SMART on FHIR auth, audit logging, PHI field encryption → Phase 3
- Full React dashboard (registry, triage queue, patient detail) → Phase 3 (Phase 1 ships only
  upload + pipeline-status UI)
- Promotion of the 5 deferred resource types to relational models → Phase 4

---

## Intervention Forecast (where user input is required)

| # | When | What | Why it's the user's call |
|---|---|---|---|
| 1 | Inc 0 | Install `uv` (or approve installer) | Touches user's machine |
| 2 | Inc 3 | Clinical sanity-check the curated crosswalk CSV | False code mappings = clinical-correctness risk |
| 3 | Inc 1 | Eyeball dev fixtures cover demo conditions | Demo narrative is the user's call |
| 4 | Inc 4 | Confirm conservative dedup thresholds | Healthcare false-merge safety judgment |
| 5 | Inc 0 | Confirm Docker Desktop ≥4GB | Local resource config |
| 6 | Phase 2 preview | LLM provider + API key; ESI Handbook PDF | Flagged early to avoid surprise |

---

## Verification (Phase 1 acceptance)

1. `docker compose up` boots api + worker + postgres + redis.
2. `POST /api/v1/bundles/upload` with a Synthea-style fixture returns a `pipeline_run_id`.
3. All 13 resource types parse without exception.
4. Crosswalk resolves top-200 conditions; diabetes patient carries both ICD-10 + SNOMED.
5. Dedup produces possible-match flags on a duplicated patient.
6. WebSocket streams stage transitions to the frontend.
7. The 2 Phase-1 clinical assertion tests pass against the test DB.
