# MedSync — Full Project Specification
## FHIR-Native Clinical Data Pipeline with AI Triage Engine

**Version:** 1.0 | **Author:** Recruiter Spec | **Build Window:** 4–5 weeks
**Complements:** AgentProof (AI infra/eval) + CompanyBrain (enterprise knowledge)

---

## 1. THE ELEVATOR PITCH

MedSync is a backend-heavy clinical data platform that ingests patient health
records in FHIR R4 format, normalizes messy real-world EHR data across
competing medical terminology systems (ICD-10, SNOMED CT, LOINC), runs an
AI-powered triage engine that prioritizes patient cases by Emergency Severity
Index (ESI) acuity levels, and exposes a clean, queryable API for downstream
clinical tools.

It is the "data infrastructure layer" every health-tech startup needs but
nobody wants to build — combined with an intelligent clinical reasoning
layer that demonstrates you can make AI work in regulated, high-stakes
domains.

**One-sentence pitch:** "I built the FHIR data pipeline and clinical AI
triage engine that sits underneath every health-tech product."

---

## 2. WHY THIS PROJECT, WHY NOW

### Market Signal: YC Summer 2026 — "AI Personalized Medicine"

YC's RFS explicitly calls for startups building for "intelligent personalized
care" — but the bottleneck isn't the AI models. It's the data layer. Every
health-tech founder reports the same problem: getting clean, structured
patient data out of EHR systems is engineering hell.

### Regulatory Tailwind: FHIR R4 is now mandatory

By 2026, FHIR R4 API compliance is a baseline regulatory expectation for
virtually every major healthcare IT system in the United States. The CMS
mandate (21st Century Cures Act) means every hospital system must expose
FHIR APIs. This creates massive demand for engineers who understand FHIR
at a systems level.

### Hiring Signal

- AI engineer salaries hit $206K average in 2026
- LLM fine-tuning, RAG, and agentic AI are the highest-premium skills
- Health-tech is the second-largest vertical for AI hiring after fintech
- Almost NO portfolio projects in the wild demonstrate FHIR competence
- Consulting firms (McKinsey QuantumBlack, BCG X) are rapidly expanding
  healthcare analytics practices

### Why This Complements Your Other Projects

| Project      | Signal                              | Domain           |
|-------------|--------------------------------------|------------------|
| AgentProof  | AI infrastructure, eval methodology  | Dev tools        |
| CompanyBrain | Enterprise knowledge systems, MCP   | Enterprise AI    |
| **MedSync** | **Domain-specific data engineering + clinical AI** | **Health-tech** |

AgentProof says: "I build the measurement layer."
CompanyBrain says: "I build the knowledge layer."
MedSync says: "I apply all of it to a domain where mistakes have
consequences, the data is genuinely hard, and regulatory compliance isn't
optional."

---

## 3. KEY FEATURES — THE FIVE PILLARS

### Pillar 1: FHIR R4 Ingestion & Normalization Pipeline

**What it does:**
- Accepts FHIR R4 Bundles (JSON) — the standard output of every modern EHR
- Parses 13+ FHIR resource types: Patient, Condition, Observation,
  Encounter, MedicationRequest, Procedure, DiagnosticReport, AllergyIntolerance,
  Immunization, CarePlan, CareTeam, Claim, Device
- Validates resources against FHIR R4 schema using `fhir.resources` (Pydantic-powered)
- Normalizes across medical terminology systems:
  - ICD-10-CM (diagnoses) — e.g., "E11.9" = Type 2 Diabetes
  - SNOMED CT (clinical findings) — e.g., "44054006" = Type 2 Diabetes
  - LOINC (lab observations) — e.g., "4548-4" = HbA1c
  - RxNorm (medications) — e.g., "860975" = Metformin 500mg
- Handles real-world data messiness: missing fields, inconsistent coding,
  duplicate records, malformed references between resources

**Why this is impressive:**
Most developers have never touched healthcare data standards. Building a
pipeline that can ingest a raw Synthea FHIR Bundle and produce clean,
normalized, queryable patient records — mapping across ICD-10, SNOMED, and
LOINC simultaneously — is genuinely difficult engineering work that health-tech
companies desperately need.

**Interview-depth detail:** The cross-terminology mapping. ICD-10 and SNOMED CT
overlap but aren't equivalent. "E11.9" in ICD-10 maps to multiple SNOMED
concepts. You need to handle one-to-many mappings, choose the most specific
match, and maintain provenance (which system did the original data come from?).

---

### Pillar 2: Probabilistic Patient Deduplication

**What it does:**
- Real-world EHR data has duplicate patient records (typos, nicknames,
  address changes, merged/split records from hospital transfers)
- Implements Fellegi-Sunter probabilistic record linkage:
  - Blocking: reduce comparison space using phonetic keys (Soundex/Metaphone on names)
  - Scoring: weighted field comparisons (name similarity via Jaro-Winkler,
    DOB exact match, address token overlap, SSN partial match)
  - Classification: match/non-match/possible-match thresholds
- Produces a deduplicated patient index with linkage confidence scores

**Why this is impressive:**
This is a real data engineering problem that every health system faces.
Probabilistic record linkage is used at Epic, Cerner, and every health
information exchange. It's a genuine algorithm (not an LLM wrapper) that
demonstrates you understand data quality at scale.

**Interview-depth detail:** The Jaro-Winkler vs. Levenshtein tradeoff for
name matching. Jaro-Winkler weights prefix matches higher, which is better
for names ("Catherine" vs "Catharine") than generic edit distance. You should
be able to explain why you chose specific weights for each field comparator.

---

### Pillar 3: AI Clinical Triage Engine (ESI-Based)

**What it does:**
- Implements the Emergency Severity Index (ESI) v5 algorithm — a 5-level
  triage system used in 94% of US emergency departments
- Four decision points, applied in order:
  1. Does this patient require immediate life-saving intervention? → ESI 1
  2. Is this a high-risk situation? Should this patient wait? → ESI 2
  3. How many resources will this patient need?
     - 2+ resources → ESI 3
     - 1 resource → ESI 4
     - 0 resources → ESI 5
  4. Are vital signs in the danger zone? (can upgrade ESI 3→2)
- **Hybrid approach — deterministic + AI:**
  - Deterministic layer: Extracts structured vitals (HR, BP, SpO2, RR, Temp)
    and chief complaints from FHIR Observations and Encounters. Applies
    rule-based ESI decision points 1, 2 (life-saving criteria), and 4
    (vital sign danger zones) using published clinical thresholds
  - AI reasoning layer (LangGraph agent): For decision point 3 (resource
    estimation) and ambiguous cases, uses RAG over ESI clinical guidelines +
    structured clinical reasoning chain to estimate resource needs and produce
    a justified triage recommendation
  - Confidence scoring: Each triage decision includes a confidence score.
    Low-confidence cases (ambiguous presentations, conflicting signals) are
    flagged for human review with pre-filled recommendations

**Why this is impressive:**
You're not just calling an LLM with "triage this patient." You're implementing
a published clinical algorithm with deterministic guardrails, using AI only
where clinical judgment is genuinely needed (resource estimation from
unstructured complaint data), and providing explainable outputs with confidence
scores. This is how clinical AI actually works in production — not black-box
LLM calls.

**Interview-depth detail:** Why the hybrid approach? Deterministic rules for
decision points 1, 2, and 4 because these have clear clinical thresholds
(HR > 100 in an adult = tachycardia, that's not a judgment call). AI for
decision point 3 because "how many resources will this patient need" requires
reasoning over the patient's history, chief complaint, and current
presentation — that's where clinical judgment lives. You should be able to
explain exactly when the LLM is invoked and when it isn't, and why.

---

### Pillar 4: RAG Over Clinical Guidelines

**What it does:**
- Ingests ESI v5 Handbook and clinical triage guidelines as the knowledge base
- Chunking strategy: section-aware splitting (respect document structure —
  don't split mid-decision-point)
- Embedding: text-embedding-3-small (OpenAI) or a local model
  (all-MiniLM-L6-v2 via sentence-transformers for cost control)
- Vector store: ChromaDB (you already know it from AgentProof)
- Retrieval pipeline:
  1. Semantic search: retrieve top-k chunks relevant to patient presentation
  2. Cross-encoder reranker (sentence-transformers cross-encoder): re-score
     retrieved chunks for precision
  3. Context assembly: combine retrieved guidelines with structured patient
     data into a reasoning prompt
- The RAG system provides the clinical knowledge the triage agent needs to
  reason about resource estimation

**Why this is impressive:**
RAG over domain-specific, structured knowledge (clinical guidelines) is
fundamentally harder than RAG over generic documents. Clinical guidelines
have precise decision trees, numbered criteria, and cross-references.
Naive chunking destroys this structure. Your section-aware chunking and
reranking pipeline shows you understand RAG beyond the tutorial level.

**Interview-depth detail:** The reranker. Initial semantic search retrieves
~20 candidate chunks. The cross-encoder reranker (which sees query + document
together, not independently) re-scores them and returns the top 3-5. You
should be able to explain why bi-encoder retrieval + cross-encoder reranking
outperforms either alone, and cite the precision improvement you measured.

---

### Pillar 5: SMART on FHIR Auth & Audit Layer

**What it does:**
- Implements SMART on FHIR OAuth 2.0 authorization scopes — the standard
  auth model for FHIR APIs in healthcare
- Scope-based access control per resource type:
  - `patient/Patient.read` — can read patient demographics
  - `patient/Observation.read` — can read vitals and lab results
  - `patient/Condition.read` — can read diagnoses
  - `user/*.read` — provider-level access to all resources
- JWT-based token issuance and validation
- Comprehensive audit logging: every data access event is logged with
  timestamp, user, resource accessed, action, and scope used
- Encryption at rest for patient data (SQLAlchemy-level field encryption
  or PostgreSQL pgcrypto)

**Why this is impressive:**
HIPAA compliance awareness in a portfolio project is extremely rare. You're
not claiming full HIPAA compliance (that requires organizational controls,
not just code), but demonstrating that you understand the authorization
model health-tech products actually use. SMART on FHIR scopes are how
Epic, Cerner, and every EHR vendor controls API access. Knowing this
signals serious health-tech understanding.

**Interview-depth detail:** SMART on FHIR scope granularity. Explain the
difference between `patient/` scopes (patient-specific, for patient-facing
apps) and `user/` scopes (provider-level, for clinical apps). Explain why
scope-based access control is preferable to role-based access control in
healthcare — because different apps need different data, and a medication
management app shouldn't see psychiatric notes even if the user has provider
credentials.

---

## 4. FULL-STACK ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                       │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ Patient   │  │ Triage Queue │  │ Patient  │  │ Upload &      │   │
│  │ Registry  │  │ (ESI Sorted) │  │ Timeline │  │ Pipeline      │   │
│  │ Dashboard │  │              │  │ View     │  │ Monitor       │   │
│  └──────────┘  └──────────────┘  └──────────┘  └───────────────┘   │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ REST API (FastAPI)
                          │ + WebSocket (pipeline status streaming)
┌─────────────────────────┴───────────────────────────────────────────┐
│                      BACKEND (FastAPI + Python)                      │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    API Layer (FastAPI)                        │    │
│  │  • FHIR Bundle upload endpoint                               │    │
│  │  • Patient CRUD + search (with FHIR-native query params)     │    │
│  │  • Triage results endpoint                                   │    │
│  │  • Pipeline status (WebSocket)                               │    │
│  │  • SMART on FHIR auth middleware                             │    │
│  │  • Audit logging middleware                                  │    │
│  └─────────────────────────┬───────────────────────────────────┘    │
│                             │                                        │
│  ┌──────────────────────────┴──────────────────────────────────┐    │
│  │              FHIR Processing Pipeline (Celery)               │    │
│  │                                                              │    │
│  │  Stage 1: Parse & Validate                                   │    │
│  │  ├─ Parse FHIR Bundle JSON                                   │    │
│  │  ├─ Validate each resource via fhir.resources (Pydantic)     │    │
│  │  └─ Extract resource references & build dependency graph     │    │
│  │                                                              │    │
│  │  Stage 2: Normalize                                          │    │
│  │  ├─ Map ICD-10 ↔ SNOMED CT ↔ LOINC codes                   │    │
│  │  ├─ Standardize units (mg/dL ↔ mmol/L, °F ↔ °C)            │    │
│  │  ├─ Resolve medication codes via RxNorm                      │    │
│  │  └─ Handle missing/malformed fields with defaults + flags    │    │
│  │                                                              │    │
│  │  Stage 3: Deduplicate                                        │    │
│  │  ├─ Blocking pass (Soundex/Metaphone on patient names)       │    │
│  │  ├─ Pairwise scoring (Jaro-Winkler name, DOB, address)       │    │
│  │  └─ Fellegi-Sunter classification → linked patient index     │    │
│  │                                                              │    │
│  │  Stage 4: Enrich & Store                                     │    │
│  │  ├─ Compute patient summary (active conditions, medications) │    │
│  │  ├─ Build clinical timeline (encounters in chronological order)│   │
│  │  └─ Write to PostgreSQL + update ChromaDB embeddings          │    │
│  └─────────────────────────┬───────────────────────────────────┘    │
│                             │                                        │
│  ┌──────────────────────────┴──────────────────────────────────┐    │
│  │              AI TRIAGE ENGINE (LangGraph)                    │    │
│  │                                                              │    │
│  │  ┌─────────────────────────────────────────────────────┐     │    │
│  │  │ Node 1: Vital Signs Extractor                       │     │    │
│  │  │ • Pull HR, BP, SpO2, RR, Temp from Observations     │     │    │
│  │  │ • Flag danger-zone vitals (deterministic thresholds) │     │    │
│  │  └───────────────────┬─────────────────────────────────┘     │    │
│  │                      ▼                                       │    │
│  │  ┌─────────────────────────────────────────────────────┐     │    │
│  │  │ Node 2: Chief Complaint Classifier                  │     │    │
│  │  │ • Extract chief complaint from Encounter.reason      │     │    │
│  │  │ • Classify: life-threatening / high-risk / standard  │     │    │
│  │  │ • Deterministic for clear cases (cardiac arrest,     │     │    │
│  │  │   stroke symptoms) → immediate ESI 1 or 2           │     │    │
│  │  └───────────────────┬─────────────────────────────────┘     │    │
│  │                      ▼                                       │    │
│  │  ┌─────────────────────────────────────────────────────┐     │    │
│  │  │ Node 3: Resource Estimation Agent (LLM + RAG)       │     │    │
│  │  │ • Retrieves relevant ESI guidelines from ChromaDB   │     │    │
│  │  │ • Cross-encoder reranks for precision                │     │    │
│  │  │ • LLM reasons about expected resource needs          │     │    │
│  │  │ • Outputs: estimated resources, reasoning chain      │     │    │
│  │  └───────────────────┬─────────────────────────────────┘     │    │
│  │                      ▼                                       │    │
│  │  ┌─────────────────────────────────────────────────────┐     │    │
│  │  │ Node 4: ESI Decision Synthesizer                    │     │    │
│  │  │ • Combines vitals + complaint + resource estimate    │     │    │
│  │  │ • Applies ESI decision tree (deterministic logic)    │     │    │
│  │  │ • Checks vital sign danger zones (can upgrade level) │     │    │
│  │  │ • Outputs: ESI level (1-5), confidence score,        │     │    │
│  │  │   reasoning trace, cited guideline sections           │     │    │
│  │  └─────────────────────────────────────────────────────┘     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    DATA LAYER                                │    │
│  │  PostgreSQL: patients, encounters, observations, conditions  │    │
│  │              triage_results, audit_log, pipeline_runs        │    │
│  │  ChromaDB:   ESI guideline embeddings, patient note embeds   │    │
│  │  Redis:      Celery broker, pipeline status cache            │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. TECH STACK WITH INTERVIEW-DEPTH ANNOTATIONS

| Layer                  | Technology                     | Why This, Not That                                                                                                  |
|------------------------|--------------------------------|---------------------------------------------------------------------------------------------------------------------|
| **Frontend**           | React 18 + Vite + TailwindCSS | You already use React/Vite. Don't learn Next.js for this — the frontend is functional, not the star. shadcn/ui for clean components. |
| **Charting**           | Recharts                       | Lightweight, React-native. For timeline views and vital sign charts. D3 is overkill here.                           |
| **Backend API**        | FastAPI (Python 3.11+)         | You already know it. Async-first, Pydantic validation (critical for FHIR resource parsing), auto-generated OpenAPI docs. |
| **FHIR Parsing**       | fhir.resources (Python)        | Pydantic-powered FHIR R4 models. Every FHIR resource type is a Python class with built-in validation. This is the standard library. |
| **Task Queue**         | Celery + Redis                 | FHIR Bundle processing is long-running (parsing 1000 patients takes seconds). Celery handles async pipeline stages. Redis as broker. |
| **AI Agent Framework** | LangGraph                      | You already know it from AgentProof. The triage engine is a 4-node graph with conditional routing — LangGraph's sweet spot. |
| **RAG Vector Store**   | ChromaDB                       | You already know it. Lightweight, embedded, no infrastructure overhead. For a portfolio project, this is the right choice over Qdrant/Pinecone. |
| **Reranker**           | sentence-transformers (cross-encoder/ms-marco-MiniLM-L-6-v2) | Lightweight cross-encoder reranker. Runs locally, no API costs. Measurable precision improvement over raw semantic search. |
| **Embeddings**         | sentence-transformers (all-MiniLM-L6-v2) OR OpenAI text-embedding-3-small | Local model for cost control in dev. OpenAI option for production quality. Make it configurable. |
| **Database**           | PostgreSQL 16                  | Relational data (patients, encounters, observations). Rich JSON support for FHIR resource storage. pgcrypto for field-level encryption. |
| **Auth**               | python-jose (JWT) + custom SMART on FHIR scope middleware | SMART on FHIR is a specific OAuth2 profile. You need custom middleware, not an off-the-shelf auth library. |
| **Record Linkage**     | recordlinkage (Python library) + custom Jaro-Winkler scorers | The `recordlinkage` library implements Fellegi-Sunter. Extend with custom comparators for healthcare-specific fields. |
| **Deployment**         | Docker Compose (FastAPI + PostgreSQL + Redis + ChromaDB) | 4-service orchestration. Single `docker compose up` for the entire stack. Deploy demo to Railway or Fly.io. |
| **Testing**            | pytest + pytest-asyncio + httpx (async API tests) | Match your AgentProof testing approach for portfolio consistency. |

---

## 6. DATA SOURCE: SYNTHEA

Synthea is an open-source synthetic patient generator maintained by MITRE.
It produces realistic (but not real) FHIR R4 Bundles with complete medical
histories.

**Why Synthea:**
- Free, no privacy/legal restrictions
- FHIR R4 native output — exactly the format you're building for
- Realistic disease progressions (diabetes → complications → medications)
- Includes 13+ resource types per patient
- Used in academic research and industry (cited in multiple papers)
- Downloadable sample datasets available (1000+ patients)

**Data plan for MedSync:**
1. Download the pre-generated FHIR R4 dataset from synthea.mitre.org
   (1000+ patients, ~2GB)
2. Use as your primary test/demo data
3. For demo purposes, focus on patients with chronic conditions
   (diabetes, hypertension, COPD) — these produce rich Observation and
   Condition resources that make triage interesting

---

## 7. PHASED BUILD PLAN (4-5 WEEKS)

### Phase 1: FHIR Pipeline Core (Days 1-10)

**Goal:** Ingest a Synthea FHIR Bundle, parse it, normalize it, store it.

**Day 1-2: Project scaffolding + FHIR models**
- [ ] Initialize monorepo: `server/` (FastAPI) + `client/` (React/Vite)
- [ ] Docker Compose: PostgreSQL + Redis + FastAPI
- [ ] SQLAlchemy models: Patient, Encounter, Observation, Condition,
      MedicationRequest, Procedure, DiagnosticReport, AllergyIntolerance
- [ ] Database migrations (Alembic)

**Day 3-5: FHIR ingestion pipeline**
- [ ] FHIR Bundle parser using `fhir.resources`
- [ ] Resource type router (Patient → patient handler, Condition → condition
      handler, etc.)
- [ ] Reference resolver (Condition references Patient, Observation
      references Encounter — resolve these into foreign keys)
- [ ] Celery task: `process_fhir_bundle` with pipeline stages
- [ ] Pipeline status tracking (Redis-backed, WebSocket to frontend)

**Day 6-8: Terminology normalization**
- [ ] ICD-10 ↔ SNOMED CT mapping table (use UMLS Metathesaurus subset or
      build a focused mapping for common conditions)
- [ ] LOINC code normalization for Observations (standardize lab names)
- [ ] Unit conversion layer (mg/dL ↔ mmol/L, °F ↔ °C)
- [ ] RxNorm medication code resolution
- [ ] Missing field handler: flag, don't reject (real-world data is messy)

**Day 9-10: Deduplication + basic API**
- [ ] Fellegi-Sunter implementation with recordlinkage library
- [ ] Blocking strategy (Soundex on last name + birth year)
- [ ] Jaro-Winkler name scorer, exact DOB scorer, address token scorer
- [ ] Match threshold configuration
- [ ] Basic FastAPI endpoints: upload bundle, list patients, get patient detail
- [ ] **Milestone:** Upload a Synthea bundle → see normalized patients in DB

---

### Phase 2: AI Triage Engine (Days 11-20)

**Goal:** Given a patient's clinical data, produce an ESI triage level
with reasoning.

**Day 11-13: Deterministic triage layer**
- [ ] Vital signs extractor: pull HR, BP, SpO2, RR, Temp from FHIR
      Observations for most recent encounter
- [ ] Danger zone classifier (published ESI thresholds):
  - Pediatric: HR/RR age-adjusted ranges
  - Adult: HR > 100, RR > 20, SpO2 < 92%, Temp > 38.5°C, SBP < 90
- [ ] Chief complaint classifier: map Encounter.reasonCode to severity
      categories (life-threatening, high-risk, standard)
- [ ] ESI decision points 1, 2, 4 (deterministic rules)

**Day 14-16: RAG pipeline for clinical guidelines**
- [ ] Ingest ESI v5 Handbook (publicly available PDF)
- [ ] Section-aware chunking (respect chapter/decision-point boundaries)
- [ ] Embed chunks → ChromaDB collection
- [ ] Retrieval function: query by patient presentation → relevant guideline sections
- [ ] Cross-encoder reranker: re-score top-20 → top-5
- [ ] Test retrieval quality: for 10 sample cases, are the right guideline
      sections retrieved?

**Day 17-19: LangGraph triage agent**
- [ ] Build 4-node LangGraph graph:
  1. `extract_vitals` → structured vital signs
  2. `classify_complaint` → severity category
  3. `estimate_resources` → LLM + RAG reasoning (decision point 3)
  4. `synthesize_decision` → final ESI level + confidence + reasoning trace
- [ ] Conditional routing: if ESI 1 or 2 from deterministic layer, skip
      resource estimation (no LLM call needed)
- [ ] Confidence scoring: based on vital sign clarity, complaint specificity,
      and LLM self-assessed certainty
- [ ] Store triage results with full reasoning trace (for auditability)

**Day 20: Integration test**
- [ ] End-to-end: Upload Synthea bundle → pipeline processes → triage engine
      scores all patients → results available via API
- [ ] Verify: ESI 1 patients have life-threatening conditions, ESI 5 patients
      have minor complaints. Spot-check against expected clinical outcomes.
- [ ] **Milestone:** Pipeline produces ESI triage levels for all patients in a bundle

---

### Phase 3: Auth, Audit & Frontend (Days 21-28)

**Goal:** SMART on FHIR auth, audit logging, polished frontend dashboard.

**Day 21-23: SMART on FHIR auth**
- [ ] JWT token issuance with FHIR scopes
  (`patient/Patient.read`, `patient/Observation.read`, etc.)
- [ ] Scope enforcement middleware: check token scopes against requested
      resource type
- [ ] Two auth personas for demo:
  - "Patient App" (limited scopes: own data only)
  - "Provider Dashboard" (broad scopes: all patient data)
- [ ] Audit logging middleware: log every data access with user, resource,
      action, timestamp, scopes

**Day 24-26: Frontend dashboard**
- [ ] Patient Registry: searchable, sortable patient list with active
      conditions and last encounter date
- [ ] Triage Queue: patients sorted by ESI level (1 = top, 5 = bottom),
      color-coded severity, confidence indicators
- [ ] Patient Detail View:
  - Demographics
  - Clinical timeline (encounters in chronological order)
  - Active conditions with ICD-10 + SNOMED codes
  - Current medications
  - Vital signs chart (Recharts line chart)
  - Triage result with ESI level, confidence, reasoning trace
- [ ] Upload Panel: drag-and-drop FHIR Bundle upload with real-time
      pipeline progress (WebSocket)

**Day 27-28: Polish + deployment**
- [ ] Pipeline status dashboard: show processing stages, record counts, errors
- [ ] Error handling: malformed FHIR resources surface clear error messages,
      don't crash the pipeline
- [ ] Docker Compose production config
- [ ] Deploy to Railway or Fly.io
- [ ] **Milestone:** Full demo-ready application

---

### Phase 4: Demo Polish & Interview Prep (Days 29-35)

**Goal:** Make it demo-able in 2 minutes and interview-defensible.

- [ ] README with architecture diagram, setup instructions, demo walkthrough
- [ ] Record a 2-minute demo video (Loom):
  1. Upload FHIR bundle → show pipeline processing
  2. Triage queue sorts patients by acuity
  3. Click into a patient → show clinical timeline, triage reasoning
  4. Show scope-based access control (patient app vs provider view)
- [ ] Write 3-5 unit tests that demonstrate pipeline correctness
  (e.g., "Synthea patient with diabetes has ICD-10 E11.x AND SNOMED 44054006")
- [ ] Prepare interview talking points (see Section 9)
- [ ] Add metrics to README: "Processed 1,000 synthetic patients in X seconds,
      average triage latency: Xms, RAG retrieval precision: X%"

---

## 8. RESUME BULLET EXAMPLES

**Primary (use this one):**
> Engineered a FHIR R4 clinical data pipeline ingesting 10K+ synthetic
> patient records with cross-terminology normalization (ICD-10 / SNOMED CT /
> LOINC), probabilistic patient deduplication (Fellegi-Sunter), and an
> AI triage engine producing ESI acuity scores via a LangGraph agent with
> RAG over clinical guidelines — FastAPI, PostgreSQL, ChromaDB, Docker

**Alternative — AI-focused (for AI lab applications):**
> Built a hybrid clinical triage system combining deterministic ESI
> decision-tree logic with a LangGraph agent using RAG over medical
> guidelines (cross-encoder reranked retrieval, ChromaDB), achieving
> clinically-aligned acuity scoring with confidence-gated human escalation

**Alternative — Data engineering-focused (for consulting firm applications):**
> Designed a healthcare data normalization pipeline processing FHIR R4
> Bundles across 13 resource types with ICD-10/SNOMED CT/LOINC
> cross-mapping, probabilistic record linkage (Jaro-Winkler + Fellegi-Sunter),
> and SMART on FHIR OAuth2 scope-based access control

---

## 9. INTERVIEW TALKING POINTS — TIER 1 (MUST KNOW COLD)

### TP1: "Why a hybrid deterministic + AI triage approach?"

"ESI triage has four decision points. Points 1, 2, and 4 have clear clinical
thresholds — cardiac arrest is always ESI 1, tachycardia with altered mental
status is always ESI 2, danger-zone vitals can always upgrade a level. These
are deterministic, and running them through an LLM would add latency, cost,
and unpredictability for zero benefit.

Decision point 3 — resource estimation — is where clinical judgment lives.
'How many resources will this patient need?' depends on the chief complaint,
history, current presentation, and what the guidelines say about similar
cases. That's a reasoning task, and it's where the LLM + RAG pipeline
earns its keep.

The hybrid approach means 60-70% of patients (clear ESI 1-2 or clear ESI 4-5)
never touch the LLM. That's faster, cheaper, and more predictable. Only the
ambiguous ESI 3 cases — where resource estimation matters — use the full
AI pipeline."

### TP2: "How does your cross-terminology normalization work?"

"Healthcare uses multiple overlapping coding systems. ICD-10 is diagnosis
codes (what the patient has). SNOMED CT is clinical findings (what you
observe). LOINC is lab tests (what you measure). They overlap but aren't
equivalent — ICD-10 E11.9 (Type 2 Diabetes, unspecified) maps to SNOMED
44054006 (Diabetes Mellitus Type 2), but SNOMED has 15+ more specific
diabetes concepts that ICD-10 doesn't distinguish.

I built a mapping layer that maintains a curated crosswalk table for the
most common 500 conditions and lab tests. For each incoming code, it
resolves to a canonical internal representation, stores the original code
with its system URI for provenance, and flags codes it can't map for
manual review. The key design decision was accepting lossy mappings with
provenance over requiring perfect 1:1 equivalence — because in practice,
you need the data to flow, and you need to know what you lost."

### TP3: "Explain your RAG pipeline for clinical guidelines"

"I chunk the ESI Handbook using section-aware splitting — each chunk
corresponds to a decision point or a clinical example, not an arbitrary
512-token window. This preserves the document's logic structure, which
matters because a split mid-decision-tree produces nonsensical context.

Retrieval is two-stage: bi-encoder semantic search retrieves the top 20
candidate chunks from ChromaDB, then a cross-encoder reranker
(ms-marco-MiniLM) re-scores them by seeing query and document together.
The cross-encoder catches cases where semantic similarity is misleading —
like a chunk about pediatric triage that mentions 'chest pain' but isn't
relevant to an adult presentation.

I measured the improvement: naive semantic search returned the correct
guideline section in the top-3 for 68% of test cases. With reranking,
that went to 87%. That 19-point improvement is the difference between a
triage system you'd trust and one you wouldn't."

### TP4: "How does probabilistic patient deduplication work?"

"Real EHR data has duplicates because patients register at multiple
facilities, names get misspelled, addresses change. Exact matching misses
most of these.

Fellegi-Sunter is a probabilistic model that scores each field comparison
independently (name similarity via Jaro-Winkler, date of birth exact
match, address token overlap), then combines them into a composite score
using log-likelihood ratios. I use a blocking pass first — group records by
Soundex of last name plus birth year — to reduce the O(n²) comparison
space to something manageable.

The key tuning decision is the match/non-match thresholds. Too aggressive
and you merge different patients (dangerous in healthcare). Too conservative
and you miss duplicates (wastes resources). I set thresholds to produce a
'possible match' middle zone that gets flagged for human review — because
in healthcare, false merges are worse than missed merges."

---

## 10. INTERVIEW TALKING POINTS — TIER 2 (KNOW WELL)

### TP5: "Why FHIR and not raw HL7 v2?"

"HL7 v2 is a pipe-delimited message format from the 1980s. It's still
in use, but it's being replaced by FHIR for API-based access. FHIR is
RESTful, JSON-native, and has a modern resource model. By 2026, FHIR R4
compliance is a regulatory requirement for US healthcare systems.

I built on FHIR because it's the direction the industry is moving, and
because the `fhir.resources` Python library gives me Pydantic-validated
resource models for free — I don't have to write parsers, I get type
safety and validation at the ingestion layer."

### TP6: "How would you scale this to production?"

"Three bottlenecks in order: (1) FHIR Bundle parsing is CPU-bound — I'd
add Celery worker scaling with autoscale based on queue depth.
(2) The deduplication step is O(n²) within each block — for millions of
patients, I'd move to a distributed blocking strategy (Spark or Dask) and
potentially use locality-sensitive hashing instead of Soundex.
(3) The LLM triage calls are latency-bound — I'd batch them, add caching
for common presentations, and consider fine-tuning a smaller model on
ESI triage data to reduce inference cost."

### TP7: "What would HIPAA compliance actually require beyond what you built?"

"What I built covers the technical safeguards — encryption at rest,
access control, audit logging. Full HIPAA requires organizational
safeguards (BAA agreements with cloud providers, employee training,
incident response plans), physical safeguards (data center controls),
and administrative safeguards (risk assessment, policies).

I also implemented field-level encryption rather than full database
encryption because HIPAA requires protecting PHI (Protected Health
Information) specifically — not all data. In production, you'd add
TLS everywhere, VPC isolation, and likely deploy on a HIPAA-eligible
cloud tier (AWS GovCloud or Azure Healthcare APIs)."

---

## 11. SKILL TRANSFERABILITY MAP

This section maps every skill demonstrated by MedSync to the specific
companies and roles where it would be relevant.

### Healthcare Data Engineering

| Skill                         | Where It Transfers                                                 |
|-------------------------------|--------------------------------------------------------------------|
| FHIR R4 parsing & validation  | Epic, Cerner (Oracle Health), athenahealth, Veracyte, any EHR vendor |
| ICD-10/SNOMED/LOINC mapping   | McKinsey QuantumBlack (healthcare practice), BCG X, Bain (healthcare consulting), any health-tech startup |
| Probabilistic record linkage  | Veracross, health information exchanges (HIEs), Datavant, any company doing entity resolution (not just healthcare) |
| FHIR data pipeline design     | Sarvam AI (health vertical), Google Health, Microsoft Health, Amazon HealthLake, Hippocratic AI |
| SMART on FHIR auth            | Any FHIR-based product company, FDA-regulated software, digital health startups |

### AI / ML Engineering

| Skill                           | Where It Transfers                                              |
|----------------------------------|-----------------------------------------------------------------|
| LangGraph multi-agent orchestration | Anthropic, OpenAI, Cohere, any AI startup using agent architectures — directly complements AgentProof |
| RAG with cross-encoder reranking | Every company building retrieval-augmented systems. This is the #1 most-demanded AI engineering skill in 2026 |
| Hybrid deterministic + LLM architecture | Palantir, Anduril, any defense-tech / decision-support company — they all use this pattern |
| Clinical AI with explainability | Hippocratic AI, Viz.ai, Abridge, Google DeepMind (health), any regulated AI deployment |
| Confidence scoring + human escalation | Critical for any production AI system. Shows you think about failure modes, not just happy paths |

### Backend / Systems Engineering

| Skill                          | Where It Transfers                                              |
|---------------------------------|-----------------------------------------------------------------|
| FastAPI async architecture      | Any Python backend role. FastAPI is the dominant Python API framework for AI companies |
| Celery + Redis async pipelines  | Any data-intensive backend: fintech (payment processing), adtech (event processing), IoT (sensor pipelines) |
| PostgreSQL + data modeling      | Universal. Every company needs this                             |
| Docker multi-service orchestration | Universal. Kubernetes is the next step, but Docker Compose demonstrates the concepts |
| JWT auth + scope-based access control | Any B2B SaaS, any API platform, any company with multi-tenant data |

### Domain Expertise Signal

| Signal                                  | Where It Transfers                                          |
|------------------------------------------|-------------------------------------------------------------|
| "I understand regulated data environments" | Healthcare, fintech (SOX, PCI-DSS), defense (ITAR, FedRAMP), legal tech |
| "I can build in domains with real consequences" | Consulting firms value this heavily — QuantumBlack and BCG X want engineers who can work with client data in sensitive domains |
| "I know healthcare interoperability standards" | This is a rare skill. Most software engineers have never heard of FHIR. It immediately differentiates you in any health-tech conversation |
| "I build AI with guardrails, not just capabilities" | Anthropic (constitutional AI), any company shipping AI to production, any company worried about AI safety in deployment |

### Cross-Project Synergies (The Portfolio Story)

| Combination                    | The Story It Tells                                          |
|--------------------------------|-------------------------------------------------------------|
| AgentProof + MedSync           | "I build AI agent infrastructure AND I apply it to regulated healthcare. The triage agent in MedSync is exactly the kind of agent AgentProof would evaluate." |
| CompanyBrain + MedSync         | "I build knowledge systems for enterprises AND I build them for clinical knowledge. The RAG pipeline in MedSync is a domain-specific version of CompanyBrain's retrieval engine." |
| All three together             | "I operate across the full AI stack: I build the eval layer (AgentProof), the knowledge layer (CompanyBrain), and the domain application layer (MedSync). I don't just build AI tools — I build AI systems that work in the real world." |

---

## 12. THE "WOW MOMENT" — DEMO SCRIPT (2 MINUTES)

**0:00 - 0:15** — "This is MedSync. It's a clinical data pipeline that
ingests raw EHR data and produces AI-powered patient triage."

**0:15 - 0:40** — Upload a Synthea FHIR Bundle (1000 patients). Show the
pipeline processing in real-time: parsing → normalizing → deduplicating →
enriching. Counter ticks up as patients are processed.

**0:40 - 1:10** — Switch to Triage Queue. Patients are sorted by ESI
acuity. ESI 1 (red) at top, ESI 5 (green) at bottom. Click into an ESI 2
patient — show their clinical timeline, vitals chart (heart rate elevated),
active conditions, and the triage reasoning: "Patient presents with chest
pain, elevated HR (112 bpm), history of coronary artery disease. ESI 2:
high-risk, should not wait. Confidence: 94%."

**1:10 - 1:30** — Click into an ESI 3 patient. Show the reasoning trace:
"Chief complaint: abdominal pain. Vitals within normal range. Based on ESI
guidelines Section 4.2, expected resources: CT scan, blood panel, physician
evaluation = 3 resources → ESI 3." Show the cited guideline section from RAG.

**1:30 - 1:50** — Show scope-based access control: switch from "Provider"
to "Patient App" persona. Patient can only see their own data. Observations
are filtered by scope. Audit log shows the access.

**1:50 - 2:00** — "The pipeline processes 1000 patients in [X] seconds.
Triage latency is [X]ms per patient. The FHIR pipeline normalizes across
ICD-10, SNOMED CT, and LOINC. Every decision is auditable."

---

## 13. WHAT TO BUILD MANUALLY vs. CLAUDE CODE-ASSISTED

### Build MANUALLY (interview-critical, must understand deeply):
- FHIR resource parsing and reference resolution logic
- Cross-terminology mapping layer (ICD-10 ↔ SNOMED CT)
- Fellegi-Sunter scoring weights and threshold configuration
- LangGraph triage agent graph definition and node logic
- ESI decision tree implementation (deterministic rules)
- SMART on FHIR scope middleware
- RAG chunking strategy (section-aware splitting)

### Use CLAUDE CODE for (boilerplate, scaffolding, repetitive):
- SQLAlchemy model definitions (many similar models)
- Alembic migration files
- FastAPI CRUD endpoints
- Docker Compose configuration
- Frontend components (React dashboard, tables, charts)
- Celery task scaffolding
- Test scaffolding and fixtures
- README and documentation

### AI-NATIVE (let the model do the heavy lifting):
- Frontend styling and layout
- Test data generation scripts
- API documentation
- Error message strings

---

## 14. RISK MITIGATION

**Risk: FHIR is too complex, rabbit-hole on edge cases**
Mitigation: Limit to 8 core resource types in Phase 1. Don't try to handle
every FHIR resource — Synthea generates the common ones. Add more resource
types only if you have time in Phase 4.

**Risk: Cross-terminology mapping is a bottomless pit**
Mitigation: Build a focused mapping table for the top 200 conditions and 100
lab tests that appear in Synthea data. Don't try to map all of ICD-10 (68,000+
codes). Link to UMLS for "see more" but curate the core set manually.

**Risk: AI triage accuracy isn't clinically valid**
Mitigation: You're not building an FDA-cleared medical device. You're
demonstrating the architecture and approach. Use Synthea data where you KNOW
the expected conditions, and validate that ESI assignments are clinically
reasonable (diabetic with DKA → ESI 2, routine checkup → ESI 5). Include
a disclaimer in the README.

**Risk: Scope creep from CompanyBrain or AgentProof**
Mitigation: MedSync is intentionally self-contained. It uses ChromaDB and
LangGraph (shared with your other projects) but doesn't depend on
AgentProof's eval framework or CompanyBrain's knowledge engine. Build it
independently. Cross-reference in interview talking points only.

---

## 15. FOLDER STRUCTURE

```
medsync/
├── server/
│   ├── medsync/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app entry
│   │   ├── config.py                  # Settings (Pydantic BaseSettings)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── patients.py        # Patient CRUD + search
│   │   │   │   ├── bundles.py         # FHIR Bundle upload
│   │   │   │   ├── triage.py          # Triage results
│   │   │   │   └── auth.py            # Token issuance
│   │   │   └── middleware/
│   │   │       ├── smart_auth.py      # SMART on FHIR scope enforcement
│   │   │       └── audit.py           # Audit logging
│   │   ├── pipeline/
│   │   │   ├── __init__.py
│   │   │   ├── tasks.py              # Celery tasks
│   │   │   ├── parser.py             # FHIR Bundle parsing
│   │   │   ├── normalizer.py         # Terminology normalization
│   │   │   ├── deduplicator.py       # Fellegi-Sunter record linkage
│   │   │   └── enricher.py           # Patient summary computation
│   │   ├── triage/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # LangGraph triage agent
│   │   │   ├── vitals.py             # Vital sign extraction & danger zones
│   │   │   ├── complaints.py         # Chief complaint classifier
│   │   │   ├── esi_rules.py          # Deterministic ESI decision tree
│   │   │   └── rag.py                # RAG retrieval + reranking
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── database.py           # SQLAlchemy models
│   │   │   └── schemas.py            # Pydantic API schemas
│   │   ├── terminology/
│   │   │   ├── __init__.py
│   │   │   ├── icd10.py              # ICD-10 code utilities
│   │   │   ├── snomed.py             # SNOMED CT utilities
│   │   │   ├── loinc.py              # LOINC code utilities
│   │   │   ├── rxnorm.py             # RxNorm medication codes
│   │   │   └── crosswalk.py          # Cross-terminology mapping
│   │   └── db/
│   │       ├── session.py            # Async SQLAlchemy session
│   │       └── migrations/           # Alembic
│   ├── tests/
│   │   ├── test_parser.py
│   │   ├── test_normalizer.py
│   │   ├── test_deduplicator.py
│   │   ├── test_triage.py
│   │   └── test_api.py
│   ├── data/
│   │   ├── synthea/                  # Sample FHIR Bundles
│   │   ├── terminology/              # Mapping tables (CSV)
│   │   └── guidelines/               # ESI Handbook chunks
│   ├── pyproject.toml
│   └── Dockerfile
├── client/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   │   ├── PatientRegistry.jsx
│   │   │   ├── TriageQueue.jsx
│   │   │   ├── PatientDetail.jsx
│   │   │   └── UploadPanel.jsx
│   │   ├── components/
│   │   │   ├── VitalsChart.jsx
│   │   │   ├── ClinicalTimeline.jsx
│   │   │   ├── TriageCard.jsx
│   │   │   └── PipelineStatus.jsx
│   │   └── hooks/
│   │       ├── useWebSocket.js
│   │       └── usePatients.js
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
├── README.md
└── Makefile                          # make up, make seed, make test
```

---

## END OF SPECIFICATION

This document is your build reference. Follow the phases in order.
The FHIR pipeline is Phase 1 because it's the foundation everything
else sits on. The AI triage engine is Phase 2 because it's the "wow
factor." Auth and frontend are Phase 3 because they're necessary for
demo but not the technical differentiator.

When in doubt about scope: cut frontend features, never cut backend depth.
The backend is where the hiring signal lives.