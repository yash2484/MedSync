"""Live end-to-end verification of the Increment 1 spine.

Run AFTER `docker compose up` (api on :8000, worker, postgres, redis):

    server\\.venv\\Scripts\\python.exe scripts\\verify_spine.py

Uploads the diabetes fixture, waits for the pipeline run to complete, then
confirms the patient + conditions are queryable. Exits non-zero on failure.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
FIXTURE = Path(__file__).resolve().parent.parent / "data" / "synthea" / "fixture_diabetes_patient.json"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=10.0) as client:
        assert client.get("/health").json() == {"status": "ok"}, "health check failed"

        with FIXTURE.open("rb") as fh:
            resp = client.post("/api/v1/bundles/upload", files={"file": (FIXTURE.name, fh, "application/json")})
        resp.raise_for_status()
        run_id = resp.json()["pipeline_run_id"]
        print(f"uploaded -> pipeline_run_id={run_id}")

        for _ in range(30):
            run = client.get(f"/api/v1/bundles/{run_id}").json()
            if run["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)
        print(f"run status={run['status']} stage={run['current_stage']} "
              f"records={run['record_count']} errors={run['error_count']}")
        if run["status"] != "completed":
            print("FAIL: pipeline did not complete")
            return 1

        patients = client.get("/api/v1/patients").json()
        shaq = next((p for p in patients if p["family_name"] == "O'Neal"), None)
        if not shaq:
            print("FAIL: Shaq not found in patient registry")
            return 1

        detail = client.get(f"/api/v1/patients/{shaq['id']}").json()
        n_conditions = len(detail["conditions"])
        print(f"patient: {detail['given_name']} {detail['family_name']} "
              f"({detail['gender']}) — {n_conditions} conditions")
        if n_conditions != 2:
            print(f"FAIL: expected 2 conditions, got {n_conditions}")
            return 1

        print("\nPASS: upload -> parse -> store -> API verified end-to-end.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
