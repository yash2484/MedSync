"""Live verification for Increment 3: Stage 2 normalization.

Run AFTER `docker compose up -d` (applies migration 0003 on api start):

    server\\.venv\\Scripts\\python.exe scripts\\verify_normalization.py

Uploads the diabetes fixture, waits for parse+normalize to complete, then
confirms the diabetes condition carries BOTH SNOMED 44054006 and ICD-10 E11.x.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
FIXTURE = Path(__file__).resolve().parent.parent / "data" / "synthea" / "fixture_diabetes_patient.json"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15.0) as client:
        with FIXTURE.open("rb") as fh:
            resp = client.post(
                "/api/v1/bundles/upload",
                files={"file": (FIXTURE.name, fh, "application/json")},
            )
        resp.raise_for_status()
        run_id = resp.json()["pipeline_run_id"]

        for _ in range(40):
            run = client.get(f"/api/v1/bundles/{run_id}").json()
            if run["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)
        print(f"run {run_id}: status={run['status']} stage={run['current_stage']}")
        if run["status"] != "completed":
            print("FAIL: pipeline did not complete")
            return 1

        patients = client.get("/api/v1/patients").json()
        shaq = next((p for p in patients if p["family_name"] == "O'Neal"), None)
        if not shaq:
            print("FAIL: Shaq not found")
            return 1

        detail = client.get(f"/api/v1/patients/{shaq['id']}").json()
        diabetes = next((c for c in detail["conditions"] if c["code"] == "44054006"), None)
        if not diabetes:
            print("FAIL: diabetes condition not found")
            return 1

        print(f"diabetes condition: snomed={diabetes['snomed_code']} "
              f"icd10={diabetes['icd10_code']} normalized={diabetes['normalized']} "
              f"confidence={diabetes['mapping_confidence']}")
        if diabetes["snomed_code"] != "44054006" or not (diabetes["icd10_code"] or "").startswith("E11"):
            print("FAIL: diabetes condition missing both SNOMED + ICD-10")
            return 1

        print("\nPASS: normalization produced both SNOMED + ICD-10 with provenance.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
