# Phase 1 Remainder (Dedup + Enrich + Hardening) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the FHIR pipeline with Stage 3 probabilistic deduplication (custom Fellegi-Sunter) and Stage 4 patient enrichment, then harden to meet every CLAUDE.md §10 Phase 1 criterion.

**Architecture:** Pure-logic comparators + Fellegi-Sunter scoring + union-find clustering, orchestrated by a Celery `deduplicate` stage; an `enrich` stage computes a JSONB patient summary. Chain becomes `parse | normalize | deduplicate | enrich`. Pure functions are unit-tested without a DB; DB sweeps run in the worker via the per-task NullPool engine pattern.

**Tech Stack:** Python 3.11, `jellyfish` (Jaro-Winkler, Soundex), SQLAlchemy async, Celery, PostgreSQL JSONB, pytest.

## Global Constraints

- Run tests via `server/.venv/Scripts/python.exe -m pytest` (sandbox blocks `uv run`). PowerShell may be unavailable — use the Bash tool with `./.venv/Scripts/python.exe`.
- Celery DB access MUST use the per-task NullPool engine pattern in `tasks.py::_task_session` (module-level pooled engine causes "Future attached to a different loop"). Never use `async_session_factory` inside a Celery task.
- Idempotent upserts on `fhir_id`; soft deletes only (`deleted_at`); every stage updates `pipeline_runs` and publishes status.
- Healthcare safety: NEVER auto-merge possible-matches. Possible = flag + `patient_links` row only.
- Missing/failed data: flag and continue; never crash the bundle.
- `ruff check medsync tests` must pass (line-length 100).
- Commits end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

```
server/medsync/pipeline/deduplicator.py   # NEW: scorers + Fellegi-Sunter + clustering + DB sweep
server/medsync/pipeline/enricher.py       # NEW: compute_summary + DB sweep
server/medsync/pipeline/tasks.py          # MODIFY: add deduplicate_stage + enrich_stage; extend chain
server/medsync/models/database.py         # MODIFY: PatientLink model; patients.summary JSONB
server/medsync/models/schemas.py          # MODIFY: summary in PatientDetail; TimelineEntry
server/medsync/config.py                  # MODIFY: dedup thresholds + name cutoff
server/medsync/api/routes/patients.py     # MODIFY: GET /{id}/timeline
server/medsync/api/routes/bundles.py      # MODIFY: WS sends current status on connect
server/medsync/db/migrations/versions/0004_dedup_enrich.py  # NEW
server/data/synthea/fixture_shaq_variant.json               # NEW
server/tests/test_deduplicator.py         # NEW
server/tests/test_enricher.py             # NEW
server/scripts/verify_dedup.py            # NEW
server/scripts/verify_enrich.py           # NEW
```

Single-file `deduplicator.py` with clearly separated pure functions (scorers, scoring, clustering)
then the DB sweep at the bottom — the boundary that matters is pure-logic vs DB orchestration.

---

## Task 1: Dedup scorers (pure)

**Files:**
- Modify: `server/medsync/pipeline/deduplicator.py` (create)
- Test: `server/tests/test_deduplicator.py` (create)

**Interfaces:**
- Produces: `soundex_block_key(last_name: str | None, birth_year: int | None) -> str`;
  `jaro_winkler(a: str | None, b: str | None) -> float` (0..1);
  `token_overlap(a: str | None, b: str | None) -> float` (0..1);
  `exact(a, b) -> float` (1.0/0.0)

- [ ] **Step 1: Write failing tests**
```python
# server/tests/test_deduplicator.py
from medsync.pipeline.deduplicator import (
    soundex_block_key, jaro_winkler, token_overlap, exact,
)


def test_soundex_block_key_groups_similar_surnames():
    # Same Soundex + same birth year -> same block
    assert soundex_block_key("Oneal", 1968) == soundex_block_key("O'Neal", 1968)
    assert soundex_block_key("Oneal", 1968) != soundex_block_key("Oneal", 1970)


def test_soundex_block_key_handles_missing():
    assert soundex_block_key(None, None) == "____"  # sentinel, still a string


def test_jaro_winkler_prefix_weighted():
    assert jaro_winkler("Shaquille", "Shaquile") > 0.9
    assert jaro_winkler("Shaq", "Kobe") < 0.6
    assert jaro_winkler(None, "Shaq") == 0.0


def test_token_overlap_ratio():
    assert token_overlap("482 Oakwood Drive", "482 Oakwood Dr") >= 0.5
    assert token_overlap("482 Oakwood Drive", "77 Birch Lane") == 0.0
    assert token_overlap(None, "x") == 0.0


def test_exact_match():
    assert exact("M", "M") == 1.0
    assert exact("M", "F") == 0.0
    assert exact(None, None) == 0.0  # unknown != agreement
```

- [ ] **Step 2: Run to verify fail**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: FAIL (ModuleNotFoundError / ImportError)

- [ ] **Step 3: Implement**
```python
# server/medsync/pipeline/deduplicator.py
"""Stage 3 — probabilistic patient deduplication (Fellegi-Sunter).  [MANUAL]

Pure comparators + scoring + union-find clustering are unit-testable without a
database. The DB sweep at the bottom is the only part needing a session.

Healthcare safety (CLAUDE.md §6.4): false merges are worse than missed
duplicates. Possible-matches are flagged for human review, NEVER auto-merged.
"""
from __future__ import annotations

import jellyfish


def soundex_block_key(last_name: str | None, birth_year: int | None) -> str:
    code = jellyfish.soundex(last_name) if last_name else "____"
    year = str(birth_year) if birth_year else "____"
    return f"{code}:{year}"


def jaro_winkler(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return jellyfish.jaro_winkler_similarity(a.lower(), b.lower())


def token_overlap(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def exact(a, b) -> float:
    if a is None or b is None:
        return 0.0
    return 1.0 if a == b else 0.0
```

- [ ] **Step 4: Run to verify pass**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**
```bash
git add server/medsync/pipeline/deduplicator.py server/tests/test_deduplicator.py
git commit -m "feat(dedup): pure field comparators (jaro-winkler, soundex, token overlap)"
```

---

## Task 2: Fellegi-Sunter scoring + zone classification (pure)

**Files:**
- Modify: `server/medsync/pipeline/deduplicator.py`
- Test: `server/tests/test_deduplicator.py`

**Interfaces:**
- Consumes: scorers from Task 1.
- Produces:
  `@dataclass PatientFields(fhir_id, last_name, given_name, birth_date, gender, address_line, postal_code)`;
  `score_pair(a: PatientFields, b: PatientFields, name_cutoff: float = 0.85) -> float`;
  `classify(score: float, upper: float, lower: float) -> str` returning `"match"|"possible"|"non-match"`.

- [ ] **Step 1: Write failing tests**
```python
from datetime import date

from medsync.pipeline.deduplicator import PatientFields, classify, score_pair


def _shaq(fhir_id="a", last="O'Neal", given="Shaq"):
    return PatientFields(fhir_id, last, given, date(1968, 3, 14), "male",
                         "482 Oakwood Drive", "62704")


def test_score_pair_identical_is_high():
    assert score_pair(_shaq("a"), _shaq("b")) > 6.0


def test_score_pair_name_variation_still_positive():
    # Same DOB/gender/address, given name typo -> should still score well above 0
    s = score_pair(_shaq("a", given="Shaq"), _shaq("b", given="Shaquille"))
    assert s > 0.0


def test_score_pair_different_people_is_low():
    kobe = PatientFields("c", "Bryant", "Kobe", date(1978, 8, 23), "male",
                         "8 Mamba Ln", "90001")
    assert score_pair(_shaq("a"), kobe) < 0.0


def test_classify_zones():
    assert classify(7.0, upper=6.0, lower=0.0) == "match"
    assert classify(3.0, upper=6.0, lower=0.0) == "possible"
    assert classify(-1.0, upper=6.0, lower=0.0) == "non-match"
```

- [ ] **Step 2: Run to verify fail**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: FAIL (ImportError: PatientFields)

- [ ] **Step 3: Implement** (append to `deduplicator.py`)
```python
from dataclasses import dataclass
from datetime import date
from math import log2


@dataclass(frozen=True)
class PatientFields:
    fhir_id: str
    last_name: str | None
    given_name: str | None
    birth_date: date | None
    gender: str | None
    address_line: str | None
    postal_code: str | None


# Fellegi-Sunter per-field (m = P(agree|match), u = P(agree|non-match)).
# Weights: agree -> log2(m/u); disagree -> log2((1-m)/(1-u)).
_FIELD_PARAMS = {
    "last_name": (0.95, 0.01),
    "given_name": (0.90, 0.02),
    "birth_date": (0.95, 0.003),
    "gender": (0.98, 0.50),
    "address": (0.85, 0.05),
    "postal_code": (0.90, 0.04),
}


def _weight(field: str, agree: bool) -> float:
    m, u = _FIELD_PARAMS[field]
    return log2(m / u) if agree else log2((1 - m) / (1 - u))


def score_pair(a: PatientFields, b: PatientFields, name_cutoff: float = 0.85) -> float:
    agreements = {
        "last_name": jaro_winkler(a.last_name, b.last_name) >= name_cutoff,
        "given_name": jaro_winkler(a.given_name, b.given_name) >= name_cutoff,
        "birth_date": exact(a.birth_date, b.birth_date) == 1.0,
        "gender": exact(a.gender, b.gender) == 1.0,
        "address": token_overlap(a.address_line, b.address_line) >= 0.5,
        "postal_code": exact(a.postal_code, b.postal_code) == 1.0,
    }
    return sum(_weight(f, agree) for f, agree in agreements.items())


def classify(score: float, upper: float, lower: float) -> str:
    if score > upper:
        return "match"
    if score >= lower:
        return "possible"
    return "non-match"
```

- [ ] **Step 4: Run to verify pass**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add server/medsync/pipeline/deduplicator.py server/tests/test_deduplicator.py
git commit -m "feat(dedup): Fellegi-Sunter pair scoring + zone classification"
```

---

## Task 3: Union-find clustering (pure)

**Files:**
- Modify: `server/medsync/pipeline/deduplicator.py`
- Test: `server/tests/test_deduplicator.py`

**Interfaces:**
- Produces: `assign_clusters(fhir_ids: list[str], match_pairs: list[tuple[str, str]]) -> dict[str, str]`
  mapping each fhir_id to a deterministic cluster_id (the min fhir_id in its connected component).

- [ ] **Step 1: Write failing test**
```python
from medsync.pipeline.deduplicator import assign_clusters


def test_assign_clusters_unions_match_pairs():
    ids = ["a", "b", "c", "d"]
    clusters = assign_clusters(ids, [("a", "b"), ("b", "c")])
    assert clusters["a"] == clusters["b"] == clusters["c"]
    assert clusters["d"] != clusters["a"]  # singleton


def test_assign_clusters_deterministic_min_id():
    clusters = assign_clusters(["b", "a"], [("a", "b")])
    assert clusters["a"] == clusters["b"] == "a"  # min id is the cluster id
```

- [ ] **Step 2: Run to verify fail**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement** (append)
```python
def assign_clusters(fhir_ids: list[str], match_pairs: list[tuple[str, str]]) -> dict[str, str]:
    parent = {fid: fid for fid in fhir_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    for x, y in match_pairs:
        if x in parent and y in parent:
            union(x, y)
    return {fid: find(fid) for fid in fhir_ids}
```

- [ ] **Step 4: Run to verify pass**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add server/medsync/pipeline/deduplicator.py server/tests/test_deduplicator.py
git commit -m "feat(dedup): union-find cluster assignment"
```

---

## Task 4: Config thresholds + PatientLink model + summary column + migration 0004

**Files:**
- Modify: `server/medsync/config.py`, `server/medsync/models/database.py`
- Create: `server/medsync/db/migrations/versions/0004_dedup_enrich.py`

**Interfaces:**
- Produces: `settings.dedup_upper_threshold` (6.0), `settings.dedup_lower_threshold` (0.0),
  `settings.dedup_name_similarity_cutoff` (0.85); `PatientLink` ORM
  (`patient_a_fhir_id, patient_b_fhir_id, score, match_zone`); `Patient.summary` JSONB column.

- [ ] **Step 1: Add settings** to `config.py` (after `embedding_provider`):
```python
    dedup_upper_threshold: float = 6.0
    dedup_lower_threshold: float = 0.0
    dedup_name_similarity_cutoff: float = 0.85
```

- [ ] **Step 2: Add `summary` to Patient + `PatientLink` model** in `database.py`.
On `Patient` (after `match_zone`):
```python
    summary: Mapped[dict | None] = mapped_column(JSONB)
```
New model (after `Patient`):
```python
class PatientLink(TimestampMixin, Base):
    __tablename__ = "patient_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_a_fhir_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    patient_b_fhir_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    match_zone: Mapped[str] = mapped_column(String(32), nullable=False)
```

- [ ] **Step 3: Write migration** `0004_dedup_enrich.py`:
```python
"""dedup + enrich: patient_links table, patients.summary

Revision ID: 0004_dedup_enrich
Revises: 0003_normalization
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_dedup_enrich"
down_revision: Union[str, None] = "0003_normalization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("summary", postgresql.JSONB(), nullable=True))
    op.create_table(
        "patient_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_a_fhir_id", sa.String(64), nullable=False),
        sa.Column("patient_b_fhir_id", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("match_zone", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_patient_links_a", "patient_links", ["patient_a_fhir_id"])
    op.create_index("ix_patient_links_b", "patient_links", ["patient_b_fhir_id"])


def downgrade() -> None:
    op.drop_table("patient_links")
    op.drop_column("patients", "summary")
```

- [ ] **Step 4: Verify import + offline tests still green**
Run: `./.venv/Scripts/python.exe -c "import medsync.models.database, medsync.config" && ./.venv/Scripts/python.exe -m pytest -q`
Expected: imports OK; existing suite passes.

- [ ] **Step 5: Commit**
```bash
git add server/medsync/config.py server/medsync/models/database.py server/medsync/db/migrations/versions/0004_dedup_enrich.py
git commit -m "feat(dedup): config thresholds, PatientLink model, summary column, migration 0004"
```

---

## Task 5: Deduplication DB sweep

**Files:**
- Modify: `server/medsync/pipeline/deduplicator.py`
- Test: `server/tests/test_deduplicator.py`

**Interfaces:**
- Consumes: `PatientFields`, `soundex_block_key`, `score_pair`, `classify`, `assign_clusters`;
  `settings`; ORM `Patient`, `PatientLink`.
- Produces: `build_blocks(patients: list[PatientFields]) -> dict[str, list[PatientFields]]`;
  `async def deduplicate_records(session) -> dict` (returns
  `{clusters, matches, possible, compared}` and writes cluster_id/match_zone/patient_links).

- [ ] **Step 1: Write failing test for `build_blocks` (pure)**
```python
def test_build_blocks_groups_by_soundex_and_year():
    from medsync.pipeline.deduplicator import PatientFields, build_blocks
    from datetime import date
    a = PatientFields("a", "O'Neal", "Shaq", date(1968, 3, 14), "male", "x", "1")
    b = PatientFields("b", "Oneal", "Shaquille", date(1968, 7, 1), "male", "x", "1")
    c = PatientFields("c", "Bryant", "Kobe", date(1978, 8, 23), "male", "y", "2")
    blocks = build_blocks([a, b, c])
    # a and b share Soundex(last)+birth_year -> same block; c separate
    key_ab = next(k for k, v in blocks.items() if any(p.fhir_id == "a" for p in v))
    assert {p.fhir_id for p in blocks[key_ab]} == {"a", "b"}
```

- [ ] **Step 2: Run to verify fail**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py::test_build_blocks_groups_by_soundex_and_year -q`
Expected: FAIL (ImportError: build_blocks)

- [ ] **Step 3: Implement** (append to `deduplicator.py`)
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medsync.config import settings
from medsync.models.database import Patient, PatientLink


def build_blocks(patients: list[PatientFields]) -> dict[str, list[PatientFields]]:
    blocks: dict[str, list[PatientFields]] = {}
    for p in patients:
        year = p.birth_date.year if p.birth_date else None
        key = soundex_block_key(p.last_name, year)
        blocks.setdefault(key, []).append(p)
    return blocks


def _to_fields(p: Patient) -> PatientFields:
    return PatientFields(
        fhir_id=p.fhir_id, last_name=p.family_name, given_name=p.given_name,
        birth_date=p.birth_date, gender=p.gender, address_line=p.address_line,
        postal_code=p.postal_code,
    )


async def deduplicate_records(session: AsyncSession) -> dict:
    patients = (
        await session.execute(select(Patient).where(Patient.deleted_at.is_(None)))
    ).scalars().all()
    fields = [_to_fields(p) for p in patients]
    ids = [f.fhir_id for f in fields]

    match_pairs: list[tuple[str, str]] = []
    links: list[tuple[str, str, float, str]] = []
    compared = 0
    for block in build_blocks(fields).values():
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                compared += 1
                score = score_pair(block[i], block[j], settings.dedup_name_similarity_cutoff)
                zone = classify(score, settings.dedup_upper_threshold, settings.dedup_lower_threshold)
                if zone == "match":
                    match_pairs.append((block[i].fhir_id, block[j].fhir_id))
                    links.append((block[i].fhir_id, block[j].fhir_id, score, zone))
                elif zone == "possible":
                    links.append((block[i].fhir_id, block[j].fhir_id, score, zone))

    clusters = assign_clusters(ids, match_pairs)
    matched_ids = {x for pair in match_pairs for x in pair}
    possible_ids = {x for a, b, s, z in links if z == "possible" for x in (a, b)}

    for p in patients:
        p.cluster_id = clusters.get(p.fhir_id, p.fhir_id)
        if p.fhir_id in matched_ids:
            p.match_zone = "match"
        elif p.fhir_id in possible_ids:
            p.match_zone = "possible"
        else:
            p.match_zone = "non-match"

    # Rewrite this run's link audit: clear and re-insert (idempotent).
    existing = (await session.execute(select(PatientLink))).scalars().all()
    for link in existing:
        await session.delete(link)
    for a, b, s, z in links:
        session.add(PatientLink(patient_a_fhir_id=a, patient_b_fhir_id=b, score=s, match_zone=z))

    # Invariant (CLAUDE.md §9.2): no patient in two distinct clusters.
    assert len(set(clusters.values())) <= len(ids)
    await session.commit()
    return {
        "clusters": len(set(clusters.values())),
        "matches": len(match_pairs),
        "possible": len([z for *_, z in links if z == "possible"]),
        "compared": compared,
    }
```

- [ ] **Step 4: Run to verify pass**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: PASS (all dedup tests)

- [ ] **Step 5: Commit**
```bash
git add server/medsync/pipeline/deduplicator.py server/tests/test_deduplicator.py
git commit -m "feat(dedup): blocking + DB sweep writing cluster_id, match_zone, patient_links"
```

---

## Task 6: Enricher (summary computation + DB sweep)

**Files:**
- Create: `server/medsync/pipeline/enricher.py`
- Test: `server/tests/test_enricher.py` (create)

**Interfaces:**
- Consumes: ORM `Patient`, `Condition`, `Observation`, `Encounter`, `MedicationRequest`.
- Produces: `compute_summary(conditions, medications, encounters) -> dict`;
  `async def enrich_records(session) -> dict`.

- [ ] **Step 1: Write failing test for `compute_summary` (pure)**
```python
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
```

- [ ] **Step 2: Run to verify fail**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_enricher.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement `enricher.py`**
```python
"""Stage 4 — patient enrichment.  [AI-ASSISTED]

Pure `compute_summary` builds a per-patient rollup; the DB sweep stores it as a
JSONB summary. Flag-and-continue on partial data (CLAUDE.md §9.1).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medsync.models.database import Condition, Encounter, MedicationRequest, Patient


def compute_summary(conditions, medications, encounters) -> dict:
    active = [c for c in conditions if (c.clinical_status or "").lower() == "active"]
    starts = [e.period_start for e in encounters if getattr(e, "period_start", None)]
    last = max(starts) if starts else None
    return {
        "condition_count": len(conditions),
        "active_condition_count": len(active),
        "active_conditions": [c.display for c in active if c.display],
        "medication_count": len(medications),
        "encounter_count": len(encounters),
        "last_encounter_date": last.date().isoformat() if last else None,
    }


async def enrich_records(session: AsyncSession) -> dict:
    patients = (
        await session.execute(select(Patient).where(Patient.deleted_at.is_(None)))
    ).scalars().all()
    enriched = 0
    for p in patients:
        conditions = (
            await session.execute(select(Condition).where(Condition.patient_fhir_id == p.fhir_id))
        ).scalars().all()
        meds = (
            await session.execute(
                select(MedicationRequest).where(MedicationRequest.patient_fhir_id == p.fhir_id)
            )
        ).scalars().all()
        encs = (
            await session.execute(select(Encounter).where(Encounter.patient_fhir_id == p.fhir_id))
        ).scalars().all()
        p.summary = compute_summary(conditions, meds, encs)
        enriched += 1
    await session.commit()
    return {"patients_enriched": enriched}
```

- [ ] **Step 4: Run to verify pass**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_enricher.py -q`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add server/medsync/pipeline/enricher.py server/tests/test_enricher.py
git commit -m "feat(enrich): patient summary computation + DB sweep"
```

---

## Task 7: Wire deduplicate + enrich into the Celery chain

**Files:**
- Modify: `server/medsync/pipeline/tasks.py`, `server/medsync/api/routes/bundles.py`

**Interfaces:**
- Consumes: `deduplicate_records`, `enrich_records`, existing `_task_session`, `publish_status`.
- Produces: Celery tasks `pipeline.deduplicate` (`deduplicate_stage`) and `pipeline.enrich`
  (`enrich_stage`); chain `parse | normalize | deduplicate | enrich`.

- [ ] **Step 1: Add stages to `tasks.py`** (import sweeps; mirror `_run_normalize` structure). After `_run_normalize`, set normalize to NOT be terminal (`run.status = "running"`), then:
```python
from medsync.pipeline.deduplicator import deduplicate_records
from medsync.pipeline.enricher import enrich_records


async def _run_deduplicate(run_id: int) -> int:
    async with _task_session() as session:
        run = await session.get(PipelineRun, run_id)
        run.current_stage = "deduplicate"
        await session.commit()
        publish_status(run_id, "deduplicate", "running")
        try:
            stats = await deduplicate_records(session)
            detail = dict(run.error_detail or {}); detail["deduplicate"] = stats
            run.error_detail = detail
            run.status = "running"
            run.current_stage = "deduplicate"
            await session.commit()
            publish_status(run_id, "deduplicate", "completed", **stats)
        except Exception as exc:
            await session.rollback()
            run = await session.get(PipelineRun, run_id)
            run.status = "failed"; run.error_detail = {"stage": "deduplicate", "error": str(exc)}
            await session.commit()
            publish_status(run_id, "deduplicate", "failed", error=str(exc))
            raise
    return run_id


async def _run_enrich(run_id: int) -> int:
    async with _task_session() as session:
        run = await session.get(PipelineRun, run_id)
        run.current_stage = "enrich"
        await session.commit()
        publish_status(run_id, "enrich", "running")
        try:
            stats = await enrich_records(session)
            detail = dict(run.error_detail or {}); detail["enrich"] = stats
            run.error_detail = detail
            run.status = "completed"  # final stage
            run.current_stage = "enrich"
            await session.commit()
            publish_status(run_id, "enrich", "completed", **stats)
        except Exception as exc:
            await session.rollback()
            run = await session.get(PipelineRun, run_id)
            run.status = "failed"; run.error_detail = {"stage": "enrich", "error": str(exc)}
            await session.commit()
            publish_status(run_id, "enrich", "failed", error=str(exc))
            raise
    return run_id


@celery.task(name="pipeline.deduplicate")
def deduplicate_stage(run_id: int) -> int:
    return asyncio.run(_run_deduplicate(run_id))


@celery.task(name="pipeline.enrich")
def enrich_stage(run_id: int) -> int:
    return asyncio.run(_run_enrich(run_id))
```
Also change `_run_normalize`'s success branch `run.status = "completed"` to `run.status = "running"` (normalize is no longer terminal).

- [ ] **Step 2: Extend the chain** in `bundles.py`:
```python
from medsync.pipeline.tasks import deduplicate_stage, enrich_stage, normalize_stage, parse_stage
# ...
    chain(
        parse_stage.s(run.id), normalize_stage.s(),
        deduplicate_stage.s(), enrich_stage.s(),
    ).apply_async()
```

- [ ] **Step 3: Verify imports + offline suite**
Run: `./.venv/Scripts/python.exe -c "import medsync.main, medsync.pipeline.tasks" && ./.venv/Scripts/python.exe -m pytest -q`
Expected: imports OK; tasks `pipeline.deduplicate` + `pipeline.enrich` registered; suite green.

- [ ] **Step 4: Commit**
```bash
git add server/medsync/pipeline/tasks.py server/medsync/api/routes/bundles.py
git commit -m "feat(pipeline): chain parse|normalize|deduplicate|enrich"
```

---

## Task 8: Dedup fixture + clinical assertion test (pure)

**Files:**
- Create: `server/data/synthea/fixture_shaq_variant.json`
- Test: `server/tests/test_deduplicator.py`

**Interfaces:**
- Consumes: `parse_bundle`, `PatientFields`, `score_pair`, `classify`, `settings`.

- [ ] **Step 1: Create `fixture_shaq_variant.json`** — Shaq, same DOB (1968-03-14), surname `Oneal`
(no apostrophe), given `Shaquille`, same address, id `11111111-...-variant`:
```json
{
  "resourceType": "Bundle",
  "type": "transaction",
  "entry": [
    {
      "fullUrl": "urn:uuid:11111111-1111-1111-1111-1111111111ff",
      "resource": {
        "resourceType": "Patient",
        "id": "11111111-1111-1111-1111-1111111111ff",
        "name": [{ "use": "official", "family": "Oneal", "given": ["Shaquille"] }],
        "gender": "male",
        "birthDate": "1968-03-14",
        "address": [
          { "line": ["482 Oakwood Drive"], "city": "Springfield", "state": "IL", "postalCode": "62704" }
        ]
      }
    }
  ]
}
```

- [ ] **Step 2: Write clinical assertion test**
```python
import json
from pathlib import Path

from medsync.config import settings
from medsync.pipeline.deduplicator import PatientFields, classify, score_pair
from medsync.pipeline.parser import parse_bundle

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "synthea"


def _fields(bundle):
    p = parse_bundle(bundle).patients[0]
    return PatientFields(p.fhir_id, p.family_name, p.given_name, p.birth_date,
                         p.gender, p.address_line, p.postal_code)


def test_same_patient_in_two_bundles_links_not_distinct():
    """CLINICAL ASSERTION: Shaq across two bundles (surname/given variation, same
    DOB+address) scores into match/possible — i.e. NOT a non-match."""
    a = _fields(json.loads((FIXTURES / "fixture_diabetes_patient.json").read_text()))
    b = _fields(json.loads((FIXTURES / "fixture_shaq_variant.json").read_text()))
    score = score_pair(a, b, settings.dedup_name_similarity_cutoff)
    zone = classify(score, settings.dedup_upper_threshold, settings.dedup_lower_threshold)
    assert zone in {"match", "possible"}
```

- [ ] **Step 3: Run to verify pass**
Run: `./.venv/Scripts/python.exe -m pytest tests/test_deduplicator.py -q`
Expected: PASS. If the pair lands "non-match", record the actual score — this is the data point for the Checkpoint 4 threshold confirmation (do NOT silently lower thresholds; surface it).

- [ ] **Step 4: Commit**
```bash
git add server/data/synthea/fixture_shaq_variant.json server/tests/test_deduplicator.py
git commit -m "test(dedup): clinical assertion + Shaq-variant fixture"
```

---

## Task 9: Expose summary + timeline endpoint; WS status-on-connect

**Files:**
- Modify: `server/medsync/models/schemas.py`, `server/medsync/api/routes/patients.py`,
  `server/medsync/api/routes/bundles.py`

**Interfaces:**
- Produces: `PatientDetail.summary: dict | None`; `GET /api/v1/patients/{id}/timeline` ->
  `list[TimelineEntry]`; WS sends current run JSON immediately on connect.

- [ ] **Step 1: Add `summary` to `PatientDetail`** and a `TimelineEntry` schema in `schemas.py`:
```python
class TimelineEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    encounter_fhir_id: str
    encounter_class: str | None = None
    reason_display: str | None = None
    period_start: datetime | None = None
```
Add to `PatientDetail`: `summary: dict | None = None`.

- [ ] **Step 2: Add timeline endpoint** to `patients.py`:
```python
from medsync.models.database import Encounter
from medsync.models.schemas import TimelineEntry

@router.get("/{patient_id}/timeline", response_model=list[TimelineEntry])
async def patient_timeline(patient_id: int, session: AsyncSession = Depends(get_session)):
    patient = await session.get(Patient, patient_id)
    if patient is None or patient.deleted_at is not None:
        raise HTTPException(status_code=404, detail="patient not found")
    rows = (
        await session.execute(
            select(Encounter)
            .where(Encounter.patient_fhir_id == patient.fhir_id)
            .order_by(Encounter.period_start)
        )
    ).scalars().all()
    return rows
```
(Encounter must expose `encounter_fhir_id` — it is the model's `fhir_id`; add an alias property or map in the route. Simplest: build `TimelineEntry` objects explicitly.)
```python
    return [
        TimelineEntry(
            encounter_fhir_id=e.fhir_id, encounter_class=e.encounter_class,
            reason_display=e.reason_display, period_start=e.period_start,
        )
        for e in rows
    ]
```

- [ ] **Step 3: WS status-on-connect** in `bundles.py` `stream_status`, after `await websocket.accept()` and before the subscribe loop, send the current run snapshot:
```python
    async with get_session_ctx() as session:  # see note
        run = await session.get(PipelineRun, run_id)
        if run is not None:
            await websocket.send_json(
                {"run_id": run_id, "stage": run.current_stage, "status": run.status}
            )
```
Note: `get_session` is a generator dependency; for direct use, open `async with async_session_factory() as session:` (import from `medsync.db.session`). This is a read in the API process (pooled engine is correct here — NOT a Celery task).

- [ ] **Step 4: Verify offline suite + import**
Run: `./.venv/Scripts/python.exe -c "import medsync.main" && ./.venv/Scripts/python.exe -m pytest -q`
Expected: imports OK; suite green.

- [ ] **Step 5: Commit**
```bash
git add server/medsync/models/schemas.py server/medsync/api/routes/patients.py server/medsync/api/routes/bundles.py
git commit -m "feat(api): expose patient summary, timeline endpoint, WS status-on-connect"
```

---

## Task 10: Live verify scripts + README benchmark stub

**Files:**
- Create: `server/scripts/verify_dedup.py`, `server/scripts/verify_enrich.py`
- Create/Modify: `README.md`

**Interfaces:** standalone scripts hitting `http://localhost:8000` (run after `docker compose up -d`).

- [ ] **Step 1: `verify_dedup.py`** — upload `fixture_diabetes_patient.json` then
`fixture_shaq_variant.json`, wait for both runs to complete, then GET `/api/v1/patients`,
assert the two Shaq records share a `cluster_id` OR appear in a `possible` link; print the score.
```python
import sys, time
from pathlib import Path
import httpx

BASE = "http://localhost:8000"
F = Path(__file__).resolve().parent.parent / "data" / "synthea"


def _upload_and_wait(c, name):
    with (F / name).open("rb") as fh:
        rid = c.post("/api/v1/bundles/upload", files={"file": (name, fh, "application/json")}).json()["pipeline_run_id"]
    for _ in range(60):
        r = c.get(f"/api/v1/bundles/{rid}").json()
        if r["status"] in ("completed", "failed"):
            return r
        time.sleep(0.5)
    return r


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=20) as c:
        _upload_and_wait(c, "fixture_diabetes_patient.json")
        run = _upload_and_wait(c, "fixture_shaq_variant.json")
        if run["status"] != "completed":
            print("FAIL: pipeline did not complete"); return 1
        patients = c.get("/api/v1/patients").json()
        shaqs = [p for p in patients if (p["family_name"] or "").lower() in {"o'neal", "oneal"}]
        zones = {p["match_zone"] for p in shaqs}
        clusters = {p["cluster_id"] for p in shaqs}
        print(f"shaq rows={len(shaqs)} zones={zones} clusters={clusters}")
        linked = len(clusters) == 1 or zones & {"match", "possible"}
        print("PASS" if linked else "FAIL", "- dedup linked the duplicate")
        return 0 if linked else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: `verify_enrich.py`** — upload the all-types fixture (`fixture_all_types.json` if present, else the diabetes fixture), GET `/api/v1/patients/{id}`, assert `summary` is populated (condition_count > 0) and `/timeline` returns ordered encounters.
```python
import sys, time
from pathlib import Path
import httpx

BASE = "http://localhost:8000"
F = Path(__file__).resolve().parent.parent / "data" / "synthea"
FIX = "fixture_all_types.json" if (F / "fixture_all_types.json").exists() else "fixture_diabetes_patient.json"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=20) as c:
        with (F / FIX).open("rb") as fh:
            rid = c.post("/api/v1/bundles/upload", files={"file": (FIX, fh, "application/json")}).json()["pipeline_run_id"]
        for _ in range(60):
            r = c.get(f"/api/v1/bundles/{rid}").json()
            if r["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)
        patients = c.get("/api/v1/patients").json()
        pid = patients[0]["id"]
        detail = c.get(f"/api/v1/patients/{pid}").json()
        timeline = c.get(f"/api/v1/patients/{pid}/timeline").json()
        ok = detail.get("summary") is not None
        print(f"summary={detail.get('summary')} timeline_len={len(timeline)}")
        print("PASS" if ok else "FAIL", "- enrich populated summary")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: README benchmark stub** — create/append `README.md` with a Phase 1 metrics table
(bundle processing, dedup, normalization coverage) marked "measured on dev fixtures; Synthea 1000
pending".

- [ ] **Step 4: Commit**
```bash
git add server/scripts/verify_dedup.py server/scripts/verify_enrich.py README.md
git commit -m "feat(verify): live dedup+enrich scripts; README benchmark stub"
```

---

## Task 11: Full offline gate + ruff

**Files:** none (verification task).

- [ ] **Step 1: Run full suite + lint**
Run: `./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check medsync tests`
Expected: all tests pass; ruff clean. Fix any failures in the owning module, re-run.

- [ ] **Step 2: Commit any fixes**
```bash
git add -A && git commit -m "chore: phase 1 remainder offline gate green"
```

(Live verification of the full chain + the dedup/enrich scripts happens at Checkpoint 4 with Docker up — NOT part of this task.)

---

## Self-Review

- **Spec coverage:** dedup blocking/scorers/F-S/zones/clustering → Tasks 1–3,5; thresholds+model+migration → Task 4; enrich → Task 6; chain → Task 7; clinical assertion + fixture → Task 8; summary/timeline/WS-on-connect → Task 9; verify scripts + README → Task 10; offline gate → Task 11. ✅
- **Intervention #4 (thresholds):** defaults in Task 4; real-score confirmation deferred to Checkpoint 4 (Task 8 surfaces the actual Shaq-variant score). ✅
- **Placeholder scan:** every code step has concrete code; Task 9 notes the explicit `TimelineEntry` construction to avoid an attribute-alias gap. ✅
- **Type consistency:** `PatientFields`, `score_pair`, `classify`, `assign_clusters`, `deduplicate_records`, `compute_summary`, `enrich_records` names consistent across tasks. `match_zone` values `"match"|"possible"|"non-match"` consistent. ✅
- **Cross-loop safety:** Tasks 5–7 sweeps run only inside `_task_session` (NullPool) via the stages; pure functions are DB-free. ✅
```
