# MedSync Phase 1 Remainder — Deduplicate + Enrich + Hardening: Design Spec

**Date:** 2026-06-11
**Status:** Approved
**Reference:** `Medsync.md`, `CLAUDE.md` §6.4 (Fellegi-Sunter), §9 (self-healing), §10 (Phase 1 done)
**Covers:** Increment 4 (Stage 3 Deduplicate + Stage 4 Enrich) and Increment 5 (Phase 1 hardening), designed as one phase-level unit.

---

## Context

Stages 1–2 of the FHIR pipeline (parse, normalize) are done and verified live. This spec completes
Phase 1: probabilistic patient **deduplication** (Stage 3) and patient **enrichment** (Stage 4),
plus the hardening needed to meet every CLAUDE.md §10 Phase 1 "done when" criterion. The chain
becomes `parse | normalize | deduplicate | enrich`.

Deduplication is interview-critical (CLAUDE.md MANUAL): probabilistic record linkage is the
data-quality problem every health system faces, and false merges in healthcare are worse than
missed duplicates.

---

## Settled Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Linkage implementation | Custom Fellegi-Sunter on `jellyfish` (Jaro-Winkler, Soundex) | `deduplicator.py` is MANUAL — must understand every line; cleaner + fully unit-testable vs wrapping `recordlinkage` pandas API. (`recordlinkage` stays in deps, unused.) |
| Enrichment storage | JSONB `summary` column on `patients`; timeline computed on read | Summary is small and queryable; derived ordering needn't be persisted. |
| Thresholds (intervention #4) | Conservative defaults in config; confirmed at Checkpoint 4 with real score distribution | Healthcare false-merge safety is the user's judgment; decide with real numbers, not blind. |

---

## Architecture

```
Stage 3 — deduplicate:
  1. Blocking: group non-deleted patients by Soundex(last_name) + birth_year
  2. Pairwise scoring within each block:
       last_name   Jaro-Winkler
       given_name  Jaro-Winkler
       birth_date  exact (1/0)
       gender      exact (1/0)
       address     token-overlap ratio
       postal_code exact (1/0)
  3. Fellegi-Sunter: per field, agree-weight = log2(m/u), disagree-weight = log2((1-m)/(1-u));
     composite = sum of per-field weights (agreement decided per-field via a similarity cutoff)
  4. Zones: composite > UPPER -> match | LOWER..UPPER -> possible | < LOWER -> non-match
  5. match pairs -> union-find -> shared cluster_id
     possible pairs -> patient_links row (flagged), NEVER merged
Stage 4 — enrich:
  per patient: summary JSONB = {active_conditions[], condition_count, medication_count,
                                encounter_count, last_encounter_date}
chain: parse | normalize | deduplicate | enrich      (enrich sets run.status=completed)
```

---

## Module Decomposition (small, single-purpose, TDD'd)

- `pipeline/deduplicator/scorers.py` — pure comparators: `jaro_winkler`, `soundex_block_key`,
  `token_overlap`, `exact`.
- `pipeline/deduplicator/fellegi_sunter.py` — pure: field weights → composite score → zone.
- `pipeline/deduplicator/clustering.py` — pure union-find over match pairs → cluster_id map.
- `pipeline/deduplicator/sweep.py` — DB orchestration: load candidates, block, score, write
  cluster_id / match_zone / patient_links.
- `pipeline/enricher.py` — pure `compute_summary(...)` + DB sweep.
- `models/database.py` — `PatientLink` model; `patients.summary` JSONB.
- `db/migrations/versions/0004_dedup_enrich.py` — `patient_links` table + `summary` column.

(If a flatter layout reads better during implementation, `deduplicator.py` may stay one file with
clearly separated pure functions — the boundary that matters is pure-logic vs DB-sweep.)

### `patient_links` schema
`id, patient_a_fhir_id, patient_b_fhir_id, score (float), match_zone (str), created_at`. The audit
trail of every non-trivial linkage decision (match + possible).

### Config (config.py)
`DEDUP_UPPER_THRESHOLD` (default 6.0), `DEDUP_LOWER_THRESHOLD` (default 0.0),
`DEDUP_NAME_SIMILARITY_CUTOFF` (default 0.85 — JW score above which a name pair "agrees").

---

## Data Flow & Scope

Deduplication compares each non-deleted patient against all others (within-bundle AND
cross-bundle/existing DB) via blocking — this is what lets "same patient uploaded in two bundles"
link. Idempotent: re-running recomputes clusters deterministically.

---

## Error Handling / Self-Healing (CLAUDE.md §9)

| Stage | On failure | Never |
|---|---|---|
| Deduplicate | log, skip the pair/record, continue | auto-merge possible-matches |
| Enrich | log, store partial summary, continue | block on missing conditions |

- Per-task NullPool async engine (the cross-loop fix) for both new Celery stages.
- §9.2 assertion after dedup: **no patient_id appears in two distinct cluster_ids.**
- Possible-match: set `match_zone='possible'` + `patient_links` row; **no data merging.**

---

## Hardening (Increment 5, folded in)

- WebSocket: send the current run status on connect (so sub-second stages aren't missed).
- Expose `summary` in `PatientDetail`; add `GET /api/v1/patients/{id}/timeline`.
- README benchmark stub (timings table).
- Full `pytest` + `ruff` green; live verify scripts for dedup + enrich.

---

## Testing (TDD)

- `test_deduplicator.py`: scorers (JW/soundex/token-overlap), Fellegi-Sunter scoring, zone
  classification, union-find clustering.
- **Clinical assertion** `test_same_patient_in_two_bundles_produces_single_linked_record`: requires
  `fixture_shaq_variant.json` (Shaq with a slight name variation, same DOB) → one cluster + a
  possible/match `patient_links` row.
- `test_enricher.py`: `compute_summary` from records (active-condition filtering, counts, last
  encounter).
- Live: `scripts/verify_dedup.py`, `scripts/verify_enrich.py`.

---

## Out of Scope (later phases)

AI triage / LangGraph / RAG (Phase 2); SMART auth / audit / PHI encryption (Phase 3); full React
dashboard (Phase 3); promotion of the 5 deferred resource types (Phase 4).

---

## Verification (Phase 1 acceptance — CLAUDE.md §10)

1. `parse | normalize | deduplicate | enrich` chain completes on a fixture.
2. Same patient in two bundles → single `cluster_id` + possible-match flag (live).
3. Dedup invariant holds: no patient in two clusters.
4. Patient summary populated; timeline endpoint returns ordered encounters.
5. All Phase 1 clinical assertion tests pass; `pytest` + `ruff` green.
6. Thresholds confirmed by user against real score distribution.
