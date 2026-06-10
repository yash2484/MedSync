# MedSync Phase 1 — FHIR Pipeline Core: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, checkpoint-batched) to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the async FHIR R4 ingestion pipeline — upload → parse → normalize → deduplicate → enrich → store — with real-time WebSocket status, as the foundation for the triage engine.

**Architecture:** FastAPI API layer accepts FHIR Bundles, enqueues a Celery chain (parse → normalize → deduplicate → enrich); each stage updates `pipeline_runs` and publishes status to Redis, which FastAPI relays over WebSocket. PostgreSQL holds 8 core relational resource types + JSONB for 5 deferred types. Vertical-slice build: prove the full async spine on Patient+Condition first, then broaden.

**Tech Stack:** FastAPI, async SQLAlchemy + asyncpg, Alembic, Celery + Redis, `fhir.resources`, `recordlinkage` + `jellyfish`, PostgreSQL 16, Docker Compose, pytest + pytest-asyncio + httpx, `uv`.

---

## Checkpoint Model

Each **Increment ends in a `🛑 CHECKPOINT`** — a hard pause where we:
1. Run the increment's verification commands together.
2. Review what was built against the spec.
3. Resolve any flagged intervention items (see the spec's Intervention Forecast).
4. Expand the *next* increment's tasks into bite-sized steps (just-in-time), then proceed.

Increment 0 below is fully expanded because we build it now. Increments 1–5 carry task-level
detail; their step-level expansion happens at the preceding checkpoint.

---

## File Structure (Phase 1)

```
server/
  pyproject.toml            # uv project + deps
  Dockerfile                # api + worker shared image
  alembic.ini
  medsync/
    __init__.py
    main.py                 # FastAPI app + /health + router includes
    config.py               # Pydantic BaseSettings (DB/Redis URLs, etc.)
    celery_app.py           # Celery instance, broker=redis
    db/
      session.py            # async engine + session factory
      base.py               # DeclarativeBase
      migrations/           # Alembic env + versions
    models/
      database.py           # SQLAlchemy ORM (8 core + raw_resources + pipeline_runs + patient_links)
      schemas.py            # Pydantic API request/response
    api/routes/
      bundles.py            # POST /bundles/upload, WS /bundles/{run_id}/status
      patients.py           # GET /patients, GET /patients/{id}
    pipeline/
      tasks.py              # Celery chain: parse|normalize|deduplicate|enrich
      parser.py             # FHIR parse + reference resolution  [MANUAL]
      normalizer.py         # terminology + unit normalization    [MANUAL]
      deduplicator.py       # Fellegi-Sunter linkage              [MANUAL]
      enricher.py           # patient summary + timeline
      status.py             # Redis publish helper
    terminology/
      crosswalk.py          # ICD-10↔SNOMED↔LOINC lookup          [MANUAL]
      units.py              # mg/dL↔mmol/L, °F↔°C
  data/
    synthea/                # dev fixtures (Claude-generated)
    terminology/            # curated crosswalk CSVs
  tests/
    conftest.py             # test DB fixtures
    test_parser.py
    test_normalizer.py
    test_deduplicator.py
    test_api.py
client/                     # minimal: upload + pipeline status only (Phase 1)
docker-compose.yml          # api, worker, postgres, redis (+ test profile)
Makefile                    # up, seed, test
```

---

## Increment 0 — Scaffolding  ⬅ BUILD NOW

**Outcome:** `docker compose up` boots api + worker + postgres + redis; `GET /health` → 200.

### Task 0.1: Repo + Python project skeleton
**Files:** Create `server/pyproject.toml`, `server/medsync/__init__.py`, `server/.python-version`

- [ ] **Step 1:** Create `server/pyproject.toml`:
```toml
[project]
name = "medsync"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "celery[redis]>=5.4",
  "redis>=5.0",
  "fhir.resources>=7.1.0",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "recordlinkage>=0.16",
  "jellyfish>=1.0",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.2", "pytest-asyncio>=0.23", "httpx>=0.27", "ruff>=0.5"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```
- [ ] **Step 2:** Create empty `server/medsync/__init__.py`; write `3.11` to `server/.python-version`.
- [ ] **Step 3 (intervention #1):** Confirm `uv` installed (`uv --version`); if missing, install via `pip install uv` or the official installer, then `cd server && uv sync --extra dev`.
- [ ] **Step 4 — Commit:** `git add server/pyproject.toml server/medsync/__init__.py server/.python-version && git commit -m "chore: scaffold server python project (uv)"`

### Task 0.2: Config
**Files:** Create `server/medsync/config.py`

- [ ] **Step 1:** Pydantic `BaseSettings` with: `database_url`, `redis_url`, `celery_broker_url`, `celery_result_backend`, `app_env`, `embedding_provider` (default `local`). Read from env with sensible Docker defaults.
- [ ] **Step 2 — Commit:** `git commit -am "feat: add config settings"`

### Task 0.3: DB layer
**Files:** Create `server/medsync/db/base.py`, `server/medsync/db/session.py`

- [ ] **Step 1:** `base.py` — `class Base(DeclarativeBase): pass`.
- [ ] **Step 2:** `session.py` — `create_async_engine(settings.database_url)`, `async_sessionmaker`, `get_session()` dependency.
- [ ] **Step 3 — Commit.**

### Task 0.4: FastAPI app + health
**Files:** Create `server/medsync/main.py`; Test `server/tests/test_health.py`

- [ ] **Step 1 (test first):**
```python
import pytest, httpx
from medsync.main import app

@pytest.mark.asyncio
async def test_health_returns_200():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```
- [ ] **Step 2:** Run `cd server && uv run pytest tests/test_health.py -v` → FAIL (no app).
- [ ] **Step 3:** `main.py` — `app = FastAPI(title="MedSync")`; `@app.get("/health")` returns `{"status":"ok"}`.
- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5 — Commit:** `git commit -am "feat: FastAPI app with /health endpoint"`

### Task 0.5: Celery app
**Files:** Create `server/medsync/celery_app.py`

- [ ] **Step 1:** `celery = Celery("medsync", broker=settings.celery_broker_url, backend=settings.celery_result_backend)`; autodiscover `medsync.pipeline.tasks`.
- [ ] **Step 2 — Commit.**

### Task 0.6: Docker Compose + Dockerfile
**Files:** Create `server/Dockerfile`, `docker-compose.yml`, `Makefile`, `server/.env.example`

- [ ] **Step 1 (intervention #5):** Confirm Docker Desktop has ≥4GB allocated.
- [ ] **Step 2:** `Dockerfile` — python:3.11-slim, install `uv`, `uv sync`, copy app.
- [ ] **Step 3:** `docker-compose.yml` — services `postgres` (postgres:16, healthcheck), `redis` (redis:7), `api` (uvicorn, depends_on healthy postgres+redis), `worker` (celery worker, same image). Named volume for pg data.
- [ ] **Step 4:** `Makefile` — `up`, `down`, `seed`, `test`, `migrate`.
- [ ] **Step 5 — Verify:** `docker compose up -d --build`; `curl localhost:8000/health` → `{"status":"ok"}`.
- [ ] **Step 6 — Commit:** `git commit -am "feat: docker-compose stack (api, worker, postgres, redis)"`

### Task 0.7: Alembic init
**Files:** Create `server/alembic.ini`, `server/medsync/db/migrations/env.py`

- [ ] **Step 1:** `uv run alembic init medsync/db/migrations`; wire `env.py` to async engine + `Base.metadata`.
- [ ] **Step 2 — Commit.**

### 🛑 CHECKPOINT 0 — Scaffolding review
**Verify together:**
```bash
docker compose up -d --build
curl -s localhost:8000/health      # → {"status":"ok"}
docker compose ps                  # → api, worker, postgres, redis all Up
cd server && uv run pytest -q      # → health test green
```
**Pause to:** confirm `uv` + Docker memory (interventions #1, #5); review compose layout; then expand Increment 1 into bite-sized steps.

---

## Increment 1 — The Spine (Patient + Condition)

**Outcome:** Upload a 2-patient fixture → patients+conditions queryable via API → live WebSocket status.

**Tasks (expanded at Checkpoint 0):**
- **1.1** ORM models: `pipeline_runs`, `patients`, `conditions` (+ `Base` metadata) → first Alembic migration.
- **1.2 (intervention #3):** Generate 2 dev fixtures in `data/synthea/` (one diabetes patient, one routine) — user eyeballs demo coverage.
- **1.3 [MANUAL] `parser.py`:** TDD — `test_parser.py::test_condition_resolves_to_patient_fk`; parse Bundle via `fhir.resources`, map `Condition.subject` ref → `patients.id`.
- **1.4 `status.py`:** Redis publish helper for `pipeline:{run_id}`.
- **1.5 `tasks.py`:** Celery `parse` task wraps parser, updates `pipeline_runs`, publishes status.
- **1.6 `bundles.py`:** `POST /api/v1/bundles/upload` (creates run, enqueues chain, returns `pipeline_run_id`); WS `/api/v1/bundles/{run_id}/status`.
- **1.7 `patients.py`:** `GET /patients`, `GET /patients/{id}`.
- **1.8:** Integration test (`test_api.py`) — upload fixture → poll run → assert patients persisted.

### 🛑 CHECKPOINT 1 — Spine review
Verify upload→parse→store→API→WebSocket end-to-end on the 2-patient fixture. Confirm fixtures match demo intent. Expand Increment 2.

---

## Increment 2 — Full Parser (all 13 types)

**Outcome:** All 13 resource types parse without exception; deferred 5 land in `raw_resources`.

**Tasks:**
- **2.1** ORM models for remaining 6 core types (`encounters, observations, medication_requests, procedures, diagnostic_reports, allergy_intolerances`) + `raw_resources` (JSONB) → migration.
- **2.2 [MANUAL]** Extend `parser.py`: full reference resolution map (`Observation.subject/encounter`, `MedicationRequest.subject/encounter`, etc.); resource-type router.
- **2.3 [MANUAL]** Missing-field policy: `has_incomplete_data=True`, store + flag, never reject (TDD: `test_missing_optional_field_is_flagged_not_rejected`).
- **2.4** Fixture exercising all 13 types; assert zero crashes; deferred types in `raw_resources`.
- **2.5** Stage-boundary assertion: `resource_type in ALLOWED_RESOURCE_TYPES`.

### 🛑 CHECKPOINT 2 — Parser review
All-13 fixture parses clean. Expand Increment 3.

---

## Increment 3 — Stage 2 Normalize

**Outcome:** Diabetes patient carries ICD-10 E11.x AND SNOMED 44054006; unmapped codes flagged.

**Tasks:**
- **3.1 (intervention #2):** Curate `data/terminology/icd10_snomed_crosswalk.csv` (top-200) + `loinc_normalized.csv` (top-100) — **user clinically sanity-checks before merge.**
- **3.2 [MANUAL] `crosswalk.py`:** loader + lookup; provenance schema `{canonical_code, canonical_system, original_code, original_system, mapping_confidence, mapping_source}`.
- **3.3 `units.py`:** mg/dL↔mmol/L, °F↔°C converters (TDD).
- **3.4 [MANUAL]** `normalize` Celery task; `normalization_failed=True` for unmapped; assertion `canonical_code is not None or normalization_failed`.
- **3.5 Clinical assertion test:** `test_diabetes_patient_has_both_icd10_and_snomed`.

### 🛑 CHECKPOINT 3 — Normalization review
Crosswalk correctness signed off; first clinical assertion test green. Expand Increment 4.

---

## Increment 4 — Stage 3 Dedup + Stage 4 Enrich

**Outcome:** Same patient (name variation) in two bundles → single `cluster_id` + possible-match flag.

**Tasks:**
- **4.1** `patient_links` model → migration.
- **4.2 [MANUAL] `deduplicator.py`:** Soundex(last_name)+birth_year blocking (`jellyfish`); Jaro-Winkler name, exact DOB, token-overlap address scorers; Fellegi-Sunter via `recordlinkage`.
- **4.3 (intervention #4):** Propose conservative match/possible/non-match thresholds — **user confirms conservativeness.**
- **4.4** Three-zone classification → `cluster_id`; possible-match → flag, never auto-merge; assertion: no patient_id in two distinct clusters.
- **4.5 `enricher.py`:** patient summary (active conditions, meds) + chronological timeline.
- **4.6 Clinical assertion test:** `test_same_patient_in_two_bundles_produces_single_linked_record`.

### 🛑 CHECKPOINT 4 — Dedup/enrich review
Thresholds approved; second clinical assertion test green. Expand Increment 5.

---

## Increment 5 — Phase 1 Hardening

**Outcome:** All CLAUDE.md §10 Phase 1 "Done when" criteria met.

**Tasks:**
- **5.1** Wire all 4 stages into the full Celery chain `parse|normalize|deduplicate|enrich`; end-to-end WebSocket status across all stages.
- **5.2** Section 9.2 validation checkpoints as runtime assertions at every stage boundary.
- **5.3** Minimal React client: UploadPanel (drag-drop) + PipelineStatus (WebSocket) only.
- **5.4** README benchmark stub (timings table) + run on dev fixtures.
- **5.5** Full `pytest` suite green; ruff clean.

### 🛑 CHECKPOINT 5 — Phase 1 acceptance
Run the spec's full Verification list (1–7). Phase 1 complete → ready for Phase 2 (AI Triage).

---

## Self-Review (against spec)

- **Spec coverage:** Pipeline stages 1–4 → Inc 1–4; all-13 parsing → Inc 2; crosswalk+provenance → Inc 3; Fellegi-Sunter+blocking+zones → Inc 4; WebSocket status → Inc 1 & 5; idempotent upserts/soft-delete → Inc 1–2 models; 2 Phase-1 clinical assertion tests → Inc 3 & 4. ✅
- **Scope contradiction (13 vs 8):** reconciled in spec + Inc 2 (parse 13, model 8, JSONB 5). ✅
- **Deferred correctly:** triage/RAG/ChromaDB → Phase 2; auth/audit/encryption → Phase 3; full dashboard → Phase 3. ✅
- **Intervention points mapped to tasks:** #1→0.1, #5→0.6, #3→1.2, #2→3.1, #4→4.3, Phase-2 preview noted. ✅
- **Placeholder scan:** Inc 0 fully expanded with code; Inc 1–5 are task-level by design (just-in-time step expansion at each checkpoint, per the user's pause-and-re-evaluate workflow). No silent TBDs.
```
