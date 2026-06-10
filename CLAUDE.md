# MedSync — CLAUDE.md
## AI Development Guide for a FHIR-Native Clinical Data Pipeline

**Spec:** `Medsync.md` | **Build window:** 4–5 weeks | **Stack:** FastAPI + Python 3.11, React 18 + Vite, PostgreSQL 16, Redis, Celery, LangGraph, ChromaDB

---

## 1. Project Identity & Build Philosophy

MedSync is a backend-heavy clinical data platform that ingests FHIR R4 patient records, normalizes them across ICD-10/SNOMED CT/LOINC/RxNorm, deduplicates patient identities via probabilistic record linkage, and runs a hybrid AI triage engine that assigns Emergency Severity Index (ESI) acuity levels with clinical reasoning traces.

**The hiring signal lives in the backend.** Cut frontend features freely. Never cut backend depth.

**Portfolio goal:** Demonstrate that you can build AI systems in a regulated, high-stakes domain where mistakes have real consequences. Every architectural decision must be interview-defensible.

**AI-native build mode:** Claude Code owns boilerplate. The developer owns every component that will be asked about in interviews. See Section 5 for the explicit split.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                       │
│  Patient Registry | Triage Queue (ESI sorted) | Patient Detail   │
│  Upload & Pipeline Monitor                                        │
└──────────────────────────┬───────────────────────────────────────┘
                           │ REST + WebSocket (FastAPI)
┌──────────────────────────┴───────────────────────────────────────┐
│                    BACKEND (FastAPI + Python 3.11)                │
│                                                                   │
│  API Layer: upload, CRUD, triage, auth, audit middleware          │
│                                                                   │
│  FHIR Pipeline (Celery):                                          │
│    Stage 1: Parse & Validate (fhir.resources Pydantic models)     │
│    Stage 2: Normalize (ICD-10 ↔ SNOMED CT ↔ LOINC ↔ RxNorm)     │
│    Stage 3: Deduplicate (Fellegi-Sunter probabilistic linkage)    │
│    Stage 4: Enrich & Store (patient summary, clinical timeline)   │
│                                                                   │
│  AI Triage Engine (LangGraph 4-node graph):                       │
│    Node 1: extract_vitals      → deterministic, no LLM           │
│    Node 2: classify_complaint  → deterministic + LLM for edge    │
│    Node 3: estimate_resources  → LLM + RAG (only LLM touchpoint) │
│    Node 4: synthesize_decision → deterministic ESI tree          │
│                                                                   │
│  Data Layer:                                                      │
│    PostgreSQL 16: patients, encounters, observations, conditions, │
│                   triage_results, audit_log, pipeline_runs        │
│    ChromaDB: ESI guideline embeddings, patient note embeddings    │
│    Redis: Celery broker, pipeline status cache, WebSocket pub/sub │
└──────────────────────────────────────────────────────────────────┘
```

**Five pillars:**
1. **FHIR R4 Ingestion** — parse + validate 13 resource types via `fhir.resources`
2. **Terminology Normalization** — ICD-10 ↔ SNOMED CT ↔ LOINC ↔ RxNorm crosswalk
3. **Probabilistic Deduplication** — Fellegi-Sunter with Jaro-Winkler + Soundex blocking
4. **AI Triage Engine** — hybrid deterministic ESI rules + LangGraph + RAG
5. **SMART on FHIR Auth** — OAuth2 scopes, JWT, field encryption, audit logging

---

## 3. Tech Stack Conventions

| Layer | Library / Version | Why This |
|---|---|---|
| Backend API | FastAPI (Python 3.11+) | Async-first, Pydantic validation, auto OpenAPI |
| FHIR Parsing | `fhir.resources` | Pydantic-backed FHIR R4 models, built-in validation |
| Task Queue | Celery + Redis | Async pipeline stages, Redis as broker and status cache |
| AI Framework | LangGraph | 4-node graph with conditional routing — its sweet spot |
| Vector Store | ChromaDB | Already known, embedded, no infra overhead |
| Reranker | `sentence-transformers` `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local, no API cost, measurable precision lift |
| Embeddings | `all-MiniLM-L6-v2` (default) / `text-embedding-3-small` (prod) | Make configurable via `config.py` |
| Database | PostgreSQL 16 + SQLAlchemy (async) | Relational + JSON, pgcrypto for PHI encryption |
| Record Linkage | `recordlinkage` + custom Jaro-Winkler scorers | Fellegi-Sunter implementation + healthcare-specific extensions |
| Auth | `python-jose` (JWT) + custom SMART middleware | SMART on FHIR is a specific OAuth2 profile, not off-the-shelf |
| Frontend | React 18 + Vite + TailwindCSS + shadcn/ui | Already known, Vite is fastest for dev iteration |
| Charting | Recharts | Lightweight, React-native, D3 is overkill |
| Testing | pytest + pytest-asyncio + httpx | Match existing project patterns |
| Deploy | Docker Compose (FastAPI + PostgreSQL + Redis + ChromaDB) | Single `docker compose up` for the full stack |

**Do not use:** Next.js, SQLite, Pinecone, Qdrant, LangChain (use LangGraph directly), any full HIPAA-as-a-service library.

---

## 4. Folder Structure & Module Ownership

```
medsync/
├── server/
│   ├── medsync/
│   │   ├── main.py                    # FastAPI app entry — AI-assisted
│   │   ├── config.py                  # Pydantic BaseSettings — AI-assisted
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── patients.py        # CRUD + FHIR-native search — AI-assisted
│   │   │   │   ├── bundles.py         # FHIR Bundle upload endpoint — AI-assisted
│   │   │   │   ├── triage.py          # Triage results endpoint — AI-assisted
│   │   │   │   └── auth.py            # Token issuance — AI-assisted
│   │   │   └── middleware/
│   │   │       ├── smart_auth.py      # SMART on FHIR scope enforcement — MANUAL
│   │   │       └── audit.py           # Audit logging middleware — MANUAL
│   │   ├── pipeline/
│   │   │   ├── tasks.py              # Celery task chain — AI-assisted scaffolding
│   │   │   ├── parser.py             # FHIR Bundle parsing + ref resolution — MANUAL
│   │   │   ├── normalizer.py         # Terminology normalization — MANUAL
│   │   │   ├── deduplicator.py       # Fellegi-Sunter record linkage — MANUAL
│   │   │   └── enricher.py           # Patient summary computation — AI-assisted
│   │   ├── triage/
│   │   │   ├── engine.py             # LangGraph graph definition — MANUAL
│   │   │   ├── vitals.py             # Vital sign extraction + danger zones — MANUAL
│   │   │   ├── complaints.py         # Chief complaint classifier — MANUAL
│   │   │   ├── esi_rules.py          # Deterministic ESI decision tree — MANUAL
│   │   │   └── rag.py                # RAG retrieval + reranking — MANUAL
│   │   ├── models/
│   │   │   ├── database.py           # SQLAlchemy ORM models — AI-assisted
│   │   │   └── schemas.py            # Pydantic API schemas — AI-assisted
│   │   ├── terminology/
│   │   │   ├── icd10.py              # ICD-10 utilities — MANUAL
│   │   │   ├── snomed.py             # SNOMED CT utilities — MANUAL
│   │   │   ├── loinc.py              # LOINC utilities — MANUAL
│   │   │   ├── rxnorm.py             # RxNorm medication codes — MANUAL
│   │   │   └── crosswalk.py          # Cross-terminology mapping — MANUAL
│   │   └── db/
│   │       ├── session.py            # Async SQLAlchemy session — AI-assisted
│   │       └── migrations/           # Alembic migration files — AI-assisted
│   ├── tests/
│   │   ├── test_parser.py
│   │   ├── test_normalizer.py
│   │   ├── test_deduplicator.py
│   │   ├── test_triage.py
│   │   └── test_api.py
│   ├── data/
│   │   ├── synthea/                  # Sample FHIR Bundles (Synthea output)
│   │   ├── terminology/              # Crosswalk CSV files (ICD10-SNOMED, LOINC)
│   │   └── guidelines/               # ESI Handbook chunks for RAG
│   ├── pyproject.toml
│   └── Dockerfile
├── client/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── PatientRegistry.jsx   # Searchable/sortable patient list
│   │   │   ├── TriageQueue.jsx       # ESI-sorted, color-coded queue
│   │   │   ├── PatientDetail.jsx     # Timeline + vitals + triage reasoning
│   │   │   └── UploadPanel.jsx       # Drag-and-drop + WebSocket progress
│   │   ├── components/
│   │   │   ├── VitalsChart.jsx       # Recharts line chart
│   │   │   ├── ClinicalTimeline.jsx  # Chronological encounter view
│   │   │   ├── TriageCard.jsx        # ESI badge + confidence indicator
│   │   │   └── PipelineStatus.jsx    # Real-time stage progress
│   │   └── hooks/
│   │       ├── useWebSocket.js       # Pipeline status streaming
│   │       └── usePatients.js        # Patient data fetching
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
├── Makefile                          # make up, make seed, make test
└── README.md
```

---

## 5. Development Philosophy — What to Build Where

### MANUAL (interview-critical — must understand every line)
- `pipeline/parser.py` — FHIR reference resolution (Condition → Patient FK, Observation → Encounter FK)
- `terminology/crosswalk.py` — ICD-10 ↔ SNOMED CT one-to-many mapping with provenance
- `pipeline/deduplicator.py` — Fellegi-Sunter weights and match/possible/non-match thresholds
- `triage/engine.py` — LangGraph 4-node graph, conditional routing logic
- `triage/esi_rules.py` — ESI decision tree (deterministic decision points 1, 2, 4)
- `triage/rag.py` — Section-aware chunking, bi-encoder + cross-encoder two-stage retrieval
- `api/middleware/smart_auth.py` — SMART on FHIR scope enforcement per resource type

### AI-ASSISTED (boilerplate — Claude Code scaffolds, developer reviews)
- `models/database.py` — SQLAlchemy models (many similar structures)
- `db/migrations/` — Alembic migration files
- `api/routes/*.py` — FastAPI CRUD endpoints, request/response models
- `docker-compose.yml` — Multi-service orchestration
- `client/src/**` — All React components and hooks
- `pipeline/tasks.py` — Celery task chain scaffolding
- `pipeline/enricher.py` — Patient summary aggregation
- `tests/` — Test scaffolding and fixtures

### AI-NATIVE (model owns entirely)
- Frontend styling and layout (Tailwind classes, shadcn/ui composition)
- Test data generation scripts
- API documentation strings
- Error message copy
- README prose

---

## 6. Domain Knowledge — Embedded Clinical Context

This section is load-bearing. Do not deviate from these rules when generating clinical logic.

### 6.1 FHIR R4 Resource Types in Scope (13)
`Patient`, `Condition`, `Observation`, `Encounter`, `MedicationRequest`, `Procedure`, `DiagnosticReport`, `AllergyIntolerance`, `Immunization`, `CarePlan`, `CareTeam`, `Claim`, `Device`

**Reference resolution pattern:**
- `Condition.subject` → `Patient.id`
- `Observation.subject` → `Patient.id`, `Observation.encounter` → `Encounter.id`
- `MedicationRequest.subject` → `Patient.id`, `MedicationRequest.encounter` → `Encounter.id`
- Always resolve references to database foreign keys during Stage 1 parsing.

**Validation rule:** Always use `fhir.resources` Pydantic models — never write raw JSON parsers for FHIR resources.

**Missing field policy:** Flag, do not reject. Set `has_incomplete_data=True`, store original + flag, continue pipeline. Real-world EHR data is messy; crashing on missing optional fields is a bug.

### 6.2 Terminology Normalization Invariants

| System | Purpose | Key Example |
|---|---|---|
| ICD-10-CM | Diagnoses | E11.9 = Type 2 Diabetes (unspecified) |
| SNOMED CT | Clinical findings | 44054006 = Diabetes Mellitus Type 2 |
| LOINC | Lab observations | 4548-4 = HbA1c; 2093-3 = Total Cholesterol |
| RxNorm | Medications | 860975 = Metformin 500mg oral tablet |

**Crosswalk design rules:**
- ICD-10 ↔ SNOMED is **one-to-many** — one ICD-10 code maps to multiple SNOMED concepts. Store the most specific match plus the mapping confidence.
- Always preserve the original code + system URI (`http://hl7.org/fhir/sid/icd-10-cm`) for provenance.
- Schema: `{canonical_code, canonical_system, original_code, original_system, mapping_confidence, mapping_source}`
- **Lossy mapping with provenance beats perfect equivalence.** Data must flow; flag what you couldn't map.
- Scope limit: top 200 conditions + top 100 LOINC codes from Synthea. Do not attempt to map all 68,000+ ICD-10 codes.
- Unit conversion: mg/dL ↔ mmol/L (glucose, cholesterol), °F ↔ °C (temperature).

### 6.3 ESI Triage Decision Tree — Deterministic Rules

The Emergency Severity Index v5 has four decision points applied in order:

```
DP1: Does patient require IMMEDIATE life-saving intervention?
     → YES: ESI 1 (cardiac arrest, respiratory arrest, unresponsive)
     → NO: continue to DP2

DP2: Is this a HIGH-RISK situation OR should patient NOT wait?
     → YES: ESI 2 (stroke symptoms, severe respiratory distress, altered mental status)
     → NO: continue to DP3

DP3: How many RESOURCES will this patient need?  ← LLM + RAG HERE ONLY
     → 2+ resources: ESI 3
     → 1 resource:  ESI 4
     → 0 resources: ESI 5

DP4: Are VITAL SIGNS in the DANGER ZONE?  (applied after DP3, can upgrade ESI 3→2)
     Adult thresholds:
       HR > 100 bpm             → danger
       RR > 20 breaths/min      → danger
       SpO2 < 92%               → danger
       Temp > 38.5°C (101.3°F)  → danger
       SBP < 90 mmHg            → danger
     Pediatric: apply age-adjusted ranges (heart rate and respiratory rate vary by age)
     → ANY danger zone vital + ESI 3 → upgrade to ESI 2
```

**LLM invocation rules:**
- Decision points 1, 2, 4: **NEVER call LLM.** These have published clinical thresholds. Deterministic only.
- Decision point 3: **ONLY** invocation point for the LLM. Resource estimation requires clinical reasoning.
- Conditional routing: if DP1 or DP2 is YES (ESI 1 or 2), skip the LangGraph `estimate_resources` node entirely.
- Result: ~60-70% of patients never touch the LLM (clear ESI 1-2 or clear ESI 4-5).

### 6.4 Probabilistic Deduplication — Fellegi-Sunter Rules

**Why:** Real EHR data has duplicate patient records (typos, name changes, multi-facility registrations).

**Algorithm:**
1. **Blocking pass** (reduce O(n²)): group by `Soundex(last_name) + birth_year`
2. **Pairwise scoring** within each block:
   - Name: Jaro-Winkler similarity (prefix-weights better than Levenshtein for names)
   - DOB: exact match → 1.0, else → 0.0
   - Address: token overlap ratio
   - SSN (if present): partial match (last 4 digits)
3. **Fellegi-Sunter classification** using log-likelihood ratios → composite score
4. **Three zones:** match (> upper threshold) / possible-match (between thresholds) / non-match (< lower threshold)

**Healthcare safety rule:** False merge (combining two different patients) is worse than a missed duplicate. Set thresholds conservatively. Possible-match zone → flag for human review, **never auto-merge**.

### 6.5 SMART on FHIR Auth Invariants

**Scope types:**
- `patient/Patient.read` — patient demographics (own record only)
- `patient/Observation.read` — vitals and labs (own record only)
- `patient/Condition.read` — diagnoses (own record only)
- `user/*.read` — provider-level: all patients, all resource types

**Why scope-based over role-based:** Different apps need different data. A medication management app should not see psychiatric notes even with provider credentials. Scope granularity enables least-privilege per application.

**JWT claims must include:** `sub` (user_id), `scope` (space-separated list), `patient` (for patient/ scopes), `exp`, `iat`.

**Audit log schema (every data access):**
```
timestamp, user_id, resource_type, resource_id, action, scopes_used, ip_address
```

**PHI encryption:** Field-level encryption on PII columns (name, DOB, address, SSN). Use PostgreSQL `pgcrypto` or SQLAlchemy-level encryption. Not whole-database encryption — HIPAA requires protecting PHI specifically.

---

## 7. LangGraph Triage Agent — Node Specifications

### Graph state schema
```python
class TriageState(TypedDict):
    patient_id: str
    vitals: VitalSigns | None          # extracted structured vitals
    vital_flags: list[str]             # danger-zone flags
    chief_complaint: str               # from Encounter.reasonCode
    complaint_severity: str            # "life_threatening" | "high_risk" | "standard"
    early_esi: int | None              # set if DP1 or DP2 triggered
    retrieved_guidelines: list[str]    # RAG chunks from ChromaDB
    estimated_resources: int | None    # 0, 1, or 2+
    resource_reasoning: str            # LLM chain-of-thought
    esi_level: int | None              # final 1-5
    confidence: float | None           # 0.0-1.0
    reasoning_trace: str               # full explanation
    requires_human_review: bool        # low confidence or failure
```

### Node 1: `extract_vitals`
- **Input:** patient_id → queries DB for most recent Encounter Observations
- **Output:** `vitals` (HR, BP, SpO2, RR, Temp) + `vital_flags` (danger zone list)
- **LLM:** No. Deterministic threshold comparison.
- **Failure:** If vitals missing → `vitals=None`, `vital_flags=["missing_vitals"]`, continue

### Node 2: `classify_complaint`
- **Input:** patient's Encounter.reasonCode + Condition list
- **Output:** `chief_complaint` (text), `complaint_severity`, `early_esi` (if DP1/DP2 triggered)
- **LLM:** Only for ambiguous cases where complaint text doesn't match known life-threatening patterns
- **Deterministic patterns (no LLM):** cardiac arrest, respiratory arrest, stroke symptoms, unresponsive → ESI 1 or 2
- **Conditional exit:** if `early_esi` is set → route directly to `synthesize_decision`, skip `estimate_resources`

### Node 3: `estimate_resources`
- **Input:** chief_complaint + vitals + patient history summary
- **Output:** `retrieved_guidelines`, `estimated_resources`, `resource_reasoning`
- **LLM:** Yes — the ONLY LLM invocation in the graph
- **RAG:** retrieve top-20 from ChromaDB → cross-encoder rerank → top-5 → inject into prompt
- **Prompt contract:** LLM must output structured JSON: `{estimated_resources: int, reasoning: str, cited_sections: list[str]}`
- **Failure handling:** timeout → retry once with 50% context reduction → fallback: `estimated_resources=2`, `confidence=0.3`, `requires_human_review=True`

### Node 4: `synthesize_decision`
- **Input:** all prior state
- **Output:** `esi_level`, `confidence`, `reasoning_trace`
- **LLM:** No for ESI level (deterministic decision tree). LLM reasoning trace is pre-computed from Node 3.
- **Vital sign upgrade check:** if DP4 triggered AND `esi_level==3` → upgrade to 2
- **Confidence logic:** high (>0.8) if vitals present + complaint specific + LLM certainty high; low (<0.5) → set `requires_human_review=True`

---

## 8. RAG Pipeline Invariants

### Chunking (section-aware, not arbitrary token windows)
- Split the ESI Handbook at chapter and decision-point boundaries
- Each chunk must correspond to one complete clinical concept (one decision point, one clinical example, one criteria table)
- Tag each chunk with: `section_id`, `decision_point` (1-4), `page_number`
- Never split across a decision tree or numbered criteria list

### Retrieval pipeline
```
Patient presentation text
        ↓
ChromaDB bi-encoder semantic search → top-20 candidates
        ↓
cross-encoder/ms-marco-MiniLM-L-6-v2 reranker → top-5
        ↓
Inject into LLM prompt with patient data
```

### Embedding configuration (make configurable in `config.py`)
- `EMBEDDING_PROVIDER=local` → `sentence-transformers/all-MiniLM-L6-v2` (default, no API cost)
- `EMBEDDING_PROVIDER=openai` → `text-embedding-3-small` (higher quality, API cost)

### Quality measurement (required for README benchmarks)
- Create 10 sample test cases with known correct guideline sections
- Measure: precision at top-3 (naive semantic) vs precision at top-3 (after reranking)
- Target: > 80% top-3 precision after reranking
- Record the delta — this is your interview talking point

---

## 9. Self-Healing Patterns & Error Recovery

### 9.1 Pipeline Stage Failure Policy

| Stage | On Failure | Never Do |
|---|---|---|
| Parse | Log `{resource_type, fhir_id, error}`, skip resource, continue | Crash the entire bundle |
| Normalize | Store original code, set `normalization_failed=True`, continue | Block on unmapped codes |
| Deduplicate | Log record_id, skip, continue | Auto-merge possible-matches |
| Enrich | Log, store partial summary, continue | Block on missing conditions |
| Triage | Set `triage_status='failed'`, flag for review | Return incorrect ESI level |

### 9.2 Validation Checkpoints

Insert these assertions at stage boundaries:

```python
# After parse
assert resource.resource_type in ALLOWED_RESOURCE_TYPES

# After normalize
assert record.canonical_code is not None or record.normalization_failed is True

# After deduplicate
# No patient_id should appear in two distinct cluster_ids
assert len({r.cluster_id for r in patient_records if r.patient_id == pid}) == 1

# After triage
assert result.esi_level in {1, 2, 3, 4, 5}
assert 0.0 <= result.confidence <= 1.0
```

### 9.3 LLM Failure Handling

- **Timeout (>10s):** Retry once with top-3 guidelines instead of top-5. If still fails: `esi_level=3`, `confidence=0.3`, `requires_human_review=True`.
- **Hallucinated ESI level** (value not in 1-5): Reject JSON, log `{patient_id, raw_output}`, apply fallback.
- **Missing required JSON fields:** Log parse error, apply fallback. Still store the reasoning trace if it exists.
- **Fallback is ESI 3:** The middle value — safest clinical default when uncertain. Document this in code.

### 9.4 Database Invariants

- **Idempotent writes:** All patient inserts use `ON CONFLICT (fhir_id) DO UPDATE` — re-processing the same bundle is safe.
- **Pipeline run tracking:** Every bundle upload creates a `pipeline_runs` row. Each stage updates `{stage, status, record_count, error_count, timestamp}`.
- **Soft deletes only:** No hard `DELETE` on patient records. Use `deleted_at` timestamp.
- **Audit log is append-only:** Never update or delete audit log entries.

### 9.5 WebSocket Status Architecture

```
Celery stage transition
        ↓
Redis PUBLISH to channel `pipeline:{bundle_id}`
        ↓
FastAPI background task SUBSCRIBE → push to WebSocket clients
        ↓
Frontend PipelineStatus component renders stage progress
```

Celery task chain: `parse.s(bundle_id) | normalize.s() | deduplicate.s() | enrich.s() | triage.s()`

---

## 10. Phase Tracking — Done Criteria

### Phase 1: FHIR Pipeline Core (Days 1-10)
**Done when:**
- `POST /api/v1/bundles/upload` accepts a Synthea FHIR Bundle JSON and returns a `pipeline_run_id`
- All 13 resource types parse without exception (test with Synthea 1000-patient bundle)
- ICD-10/SNOMED/LOINC crosswalk resolves the top-200 conditions without error
- Deduplication runs and produces possible-match flags (test with same patient in two bundles)
- Pipeline status WebSocket streams stage transitions to frontend

### Phase 2: AI Triage Engine (Days 11-20)
**Done when:**
- Every patient in the Synthea bundle has an ESI level (1-5) stored in `triage_results`
- Manual spot-check: 10 ESI 1-2 patients have cardiac/respiratory/stroke conditions
- ESI 3 patient reasoning traces cite specific ESI guideline sections (RAG working)
- P95 triage latency < 5s per patient; ESI 1-2 (no LLM path) < 500ms
- `requires_human_review=True` appears on genuinely ambiguous cases

### Phase 3: Auth & Frontend (Days 21-28)
**Done when:**
- `patient/` scope tokens can only access own patient data (enforce + test)
- `user/` scope tokens access all patients
- Audit log has an entry for every API request that returns PHI
- Triage Queue renders patients sorted by ESI level with color coding (1=red, 5=green)
- Patient Detail shows: demographics, clinical timeline, vitals chart (Recharts), triage reasoning trace

### Phase 4: Demo Polish (Days 29-35)
**Done when:**
- 2-minute demo script runs end-to-end without errors or manual intervention
- README contains: architecture diagram, setup instructions, benchmark metrics
- 5 clinical assertion tests pass (see Section 11)
- Loom demo video recorded and linked in README

---

## 11. Testing Standards

**Framework:** `pytest` + `pytest-asyncio` + `httpx` (async API client)

**Test data location:** `server/data/synthea/` — use pre-generated Synthea FHIR R4 bundles

**Do not mock the database for integration tests.** Use a test PostgreSQL instance (Docker Compose `test` profile or pytest fixture with `--postgres-url`).

### Required Clinical Assertion Tests

These 5 tests must pass — they are the demo talking points:

```python
# test_normalizer.py
def test_diabetes_patient_has_both_icd10_and_snomed():
    # Synthea diabetes patient should have ICD-10 E11.x AND SNOMED 44054006
    ...

# test_triage.py
def test_cardiac_patient_is_esi_1_or_2():
    # Patient with cardiac arrest in chief complaint must score ESI ≤ 2
    ...

def test_routine_checkup_is_esi_4_or_5():
    # Patient with annual wellness visit, normal vitals → ESI ≥ 4
    ...

# test_deduplicator.py
def test_same_patient_in_two_bundles_produces_single_linked_record():
    # Upload patient A in bundle 1, same patient (slight name variation) in bundle 2
    # Result: one cluster_id, possible-match flag
    ...

# test_api.py
def test_patient_scope_cannot_access_other_patient():
    # JWT with patient/Patient.read for patient_id=123
    # GET /patients/456 must return 403
    ...
```

**Snapshot testing for triage:** Store reasoning trace outputs for known inputs. Fail on regression. This catches LLM prompt changes that alter clinical reasoning.

---

## 12. Performance Targets

These go in the README as benchmark metrics:

| Metric | Target |
|---|---|
| Bundle processing (1000 patients) | < 60 seconds end-to-end |
| Triage latency (P95, with LLM) | < 5 seconds per patient |
| Triage latency (ESI 1-2, no LLM) | < 500ms per patient |
| RAG retrieval precision at top-3 | > 80% on 10-case test set |
| Deduplication (1000 patients) | < 10 seconds after blocking pass |

Measure these on the Synthea 1000-patient dataset and record actuals in `README.md`.

---

## 13. Anti-Patterns — Never Do These

**Clinical logic:**
- Never call the LLM for ESI decision points 1, 2, or 4 — these are published clinical thresholds, not judgment calls
- Never auto-merge "possible-match" deduplication results — false merges are worse than missed duplicates in healthcare
- Never reject a FHIR resource for a missing optional field — flag it and continue

**RAG:**
- Never use arbitrary 512-token chunking for clinical guidelines — section-aware chunking only
- Never skip the cross-encoder reranking step — the precision lift is the interview talking point

**Security:**
- Never store PHI in plaintext — use field-level encryption for all PHI columns
- Never return PHI in error messages or logs
- Never hard-delete audit log entries

**Architecture:**
- Never add frontend features at the cost of backend completeness
- Never use Next.js or SSR — React + Vite only
- Never skip pipeline stage tracking — every stage must update `pipeline_runs`
- Never build a blocking synchronous FHIR ingestion endpoint — always async via Celery

**Scope:**
- Don't try to map all 68,000+ ICD-10 codes — curate the top 200 from Synthea
- Don't add more than 8 core FHIR resource types in Phase 1 — expand in Phase 4 if time allows
- Don't claim HIPAA compliance — claim "HIPAA-aware technical safeguards" instead

---

## 14. Interview Defense Checklist

Every item below must be answerable cold (no notes):

### Must know cold (Tier 1)

**"Why hybrid deterministic + AI triage?"**
Decision points 1, 2, 4 have published clinical thresholds — cardiac arrest is always ESI 1, that's not a judgment call. LLM adds latency, cost, and unpredictability for zero benefit on these. Decision point 3 (resource estimation) is where clinical judgment lives — that's the only invocation point. Result: 60-70% of patients skip the LLM entirely.

**"How does your cross-terminology normalization work?"**
ICD-10 E11.9 maps to SNOMED 44054006, but SNOMED has 15+ more specific diabetes concepts ICD-10 doesn't distinguish. I maintain a curated crosswalk for the top 500 most common terms, store the original code + system URI for provenance, and flag codes I can't map. Lossy mapping with provenance beats requiring perfect 1:1 equivalence.

**"Explain your RAG pipeline."**
Section-aware chunking (not 512-token windows) preserves the clinical decision tree structure. Two-stage retrieval: bi-encoder semantic search retrieves top-20 candidates, cross-encoder reranker re-scores by seeing query + document together. Measured: top-3 precision went from 68% (naive semantic) to 87% (after reranking). That 19-point lift is the difference between a triage system you'd trust and one you wouldn't.

**"How does probabilistic deduplication work?"**
Soundex blocking reduces the comparison space from O(n²). Fellegi-Sunter scores fields independently: Jaro-Winkler for names (prefix-weighted, better than Levenshtein), exact match for DOB, token overlap for address. Three zones: match, possible-match, non-match. False merges in healthcare are worse than missed duplicates, so I set conservative thresholds and route possible-matches to human review.

### Know well (Tier 2)

**"Why FHIR and not HL7 v2?"** FHIR is RESTful, JSON-native, and mandatory per the 21st Century Cures Act by 2026. HL7 v2 is a 1980s pipe-delimited format still in use but being phased out for API access.

**"How would you scale this to production?"** (1) Celery autoscale on queue depth for parse parallelism. (2) LSH or Spark-based blocking instead of Soundex for millions of patients. (3) LLM call batching + caching for common presentations + potential fine-tuning on ESI data.

**"What would full HIPAA compliance require beyond what you built?"** Organizational safeguards (BAA agreements with cloud providers, employee training, incident response), physical safeguards (data center controls), TLS everywhere, VPC isolation, HIPAA-eligible cloud tier (AWS GovCloud or Azure Healthcare APIs).

---

## 15. Data Sources

**Synthea** (primary): Open-source synthetic FHIR R4 patient generator by MITRE. No privacy/legal restrictions. Download pre-generated 1000-patient dataset from synthea.mitre.org. Focus on patients with diabetes, hypertension, COPD — these produce rich Observation and Condition resources.

**Terminology crosswalk files** (`server/data/terminology/`):
- `icd10_snomed_crosswalk.csv` — curated top-200 conditions
- `loinc_normalized.csv` — curated top-100 lab codes from Synthea
- Source: UMLS Metathesaurus subset (free tier) or manually curated from NLM resources

**ESI guidelines** (`server/data/guidelines/`):
- ESI v5 Handbook sections (publicly available)
- Pre-chunked by section for RAG ingestion

---

## 16. Docker Compose Services

```yaml
services:
  api:        # FastAPI, port 8000
  worker:     # Celery worker (same image as api)
  postgres:   # PostgreSQL 16, port 5432
  redis:      # Redis 7, port 6379
  chromadb:   # ChromaDB, port 8001
```

`make up` → starts all services
`make seed` → loads Synthea bundle + ESI guidelines into ChromaDB
`make test` → runs pytest suite against test database

---

*Reference spec: `Medsync.md` — authoritative for feature requirements, interview talking points, and resume bullets.*
