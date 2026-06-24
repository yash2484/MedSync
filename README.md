# MedSync

**A FHIR-native clinical data pipeline with a hybrid AI triage engine.**

MedSync ingests FHIR R4 patient records, normalizes them across the major clinical
terminologies (ICD-10-CM, SNOMED CT, LOINC, RxNorm), deduplicates patient identities
via probabilistic record linkage, and runs a hybrid deterministic + LLM triage engine
that assigns Emergency Severity Index (ESI) acuity levels with traceable clinical
reasoning.

> ⚠️ **Work in progress.** This is an actively developed portfolio project. See
> [Current State](#current-state) for exactly what is and isn't built yet.

---

## Why this project

Healthcare data is messy, regulated, and high-stakes — the kind of domain where
"move fast and break things" doesn't fly. MedSync is built to demonstrate engineering
depth in that environment:

- **Real interoperability standards** — FHIR R4 parsing and reference resolution, not
  a toy JSON schema.
- **Clinical correctness over cleverness** — the triage engine uses published ESI
  thresholds deterministically and only calls an LLM at the single decision point that
  genuinely requires clinical judgment (resource estimation). ~60–70% of patients never
  touch the LLM.
- **Safety-first data handling** — probabilistic deduplication treats a false merge of
  two distinct patients as worse than a missed duplicate, so ambiguous matches route to
  human review and are never auto-merged.
- **Defensible architecture** — every design decision (hybrid triage, lossy-but-traceable
  terminology mapping, async pipeline, field-level PHI encryption) is made to be
  explained and justified.

All data is **synthetic** ([Synthea](https://synthea.mitre.org/)) — there is no real PHI
in this repository. MedSync implements *HIPAA-aware technical safeguards*; it does not
claim HIPAA compliance.

---

## Architecture

```
Frontend (React + Vite)
   Patient Registry · Triage Queue (ESI-sorted) · Patient Detail · Upload Monitor
        │  REST + WebSocket
Backend (FastAPI + Python 3.11)
   API layer ── async FHIR pipeline (Celery) ── AI triage engine (LangGraph)
        │
   PostgreSQL 16   ·   Redis (broker + pub/sub)   ·   ChromaDB (RAG)
```

**FHIR pipeline (Celery task chain):**

```
parse → normalize → deduplicate → enrich → triage
```

Each bundle upload creates a `pipeline_runs` row; every stage updates its status and
publishes progress to Redis, which is relayed to the frontend over a WebSocket. Writes
are idempotent (`ON CONFLICT DO UPDATE`), so re-processing the same bundle is safe.

**Five pillars:**

1. **FHIR R4 ingestion** — parse + validate 13 resource types via `fhir.resources`.
2. **Terminology normalization** — ICD-10 ↔ SNOMED CT ↔ LOINC ↔ RxNorm crosswalk with
   provenance and unit conversion.
3. **Probabilistic deduplication** — Fellegi-Sunter linkage with Jaro-Winkler + Soundex
   blocking.
4. **AI triage engine** — hybrid deterministic ESI rules + a 4-node LangGraph graph + RAG.
5. **SMART on FHIR auth** — OAuth2 scopes, JWT, field-level PHI encryption, audit logging.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI · Python 3.11 (async-first) |
| FHIR parsing | `fhir.resources` (Pydantic-backed FHIR R4 models) |
| Database | PostgreSQL 16 · async SQLAlchemy · Alembic migrations |
| Task queue | Celery + Redis (broker, status cache, WebSocket pub/sub) |
| AI framework | LangGraph (4-node triage graph) *(planned)* |
| Vector store / RAG | ChromaDB + `sentence-transformers` cross-encoder reranker *(planned)* |
| Record linkage | `recordlinkage` + custom Jaro-Winkler scorers *(planned)* |
| Auth | `python-jose` (JWT) + custom SMART on FHIR middleware *(planned)* |
| Frontend | React 18 · Vite · TailwindCSS · shadcn/ui · Recharts |
| Tooling | `uv` (packaging) · `ruff` (lint/format) · `pytest` (+ asyncio, httpx) |
| Deploy | Docker Compose (api · worker · postgres · redis · chromadb) |

---

## Getting Started

Requires Docker + Docker Compose.

```bash
make up        # build & start the full stack (api, worker, postgres, redis)
make migrate   # apply database migrations
make test      # run the pytest suite inside the api container
make logs      # tail api + worker logs
```

The API serves on `http://localhost:8000` with interactive docs at `/docs`.

**Upload a bundle and watch it process:**

```bash
curl -F "file=@server/data/synthea/fixture_diabetes_patient.json" \
  http://localhost:8000/api/v1/bundles/upload
# → { "pipeline_run_id": 1, "status": "pending" }
```

Then connect to `ws://localhost:8000/api/v1/bundles/1/status` to stream stage progress.

---

## Current State

**Phase 1 — FHIR Pipeline Core: in progress.** Increments 1–3 complete.

### ✅ Built & verified

- **Stage 1 — Parse:** all 13 FHIR R4 resource types parse without error; 8 resource
  types (Patient, Encounter, Condition, Observation, MedicationRequest, Procedure,
  DiagnosticReport, AllergyIntolerance) are modeled as first-class tables, the rest
  retained as `RawResource`. References resolved to FK columns; missing optional fields
  flagged, not rejected.
- **Stage 2 — Normalize:** ICD-10 ↔ SNOMED CT crosswalk + LOINC normalization from
  curated CSVs, with original-code provenance and mg/dL ↔ mmol/L · °F ↔ °C unit
  conversion.
- **Async pipeline:** Celery `parse → normalize` chain, idempotent upserts, per-stage
  `pipeline_runs` tracking.
- **Real-time status:** Redis pub/sub → FastAPI WebSocket streaming of stage transitions.
- **API:** `POST /api/v1/bundles/upload`, `GET /api/v1/bundles/{run_id}`,
  `WS /api/v1/bundles/{run_id}/status`, `GET /api/v1/patients`,
  `GET /api/v1/patients/{id}`.
- **Database:** PostgreSQL schema across 3 Alembic migrations.
- **Tests & checks:** ~22 passing pytest tests (parser, normalizer, health) plus 4
  standalone verification scripts (`check_invariants`, `verify_all_types`,
  `verify_normalization`, `verify_spine`).

### 🚧 Not yet built (roadmap)

| Phase | Scope |
|---|---|
| Phase 1 (remaining) | Stage 3 deduplication (Fellegi-Sunter) · Stage 4 enrichment (patient summary, clinical timeline) |
| Phase 2 | AI triage engine — LangGraph graph, deterministic ESI decision tree, RAG over ESI guidelines with cross-encoder reranking |
| Phase 3 | SMART on FHIR auth (scopes + JWT), audit logging middleware, field-level PHI encryption, frontend wiring |
| Phase 4 | Demo polish, benchmarks, end-to-end demo script |

The React frontend (pages, components, hooks) is scaffolded but not yet wired to the
live API — backend depth is the priority.

---

*Built with synthetic data for portfolio and educational purposes.*
