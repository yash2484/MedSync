"""Live verification for Increment 2: all 13 resource types persist.

Run AFTER rebuilding the stack (`docker compose up -d --build`):

    server\\.venv\\Scripts\\python.exe scripts\\verify_all_types.py

Uploads the 13-type fixture and asserts the run completes with 13 persisted
records (8 typed + 5 raw) and zero errors.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
FIXTURE = Path(__file__).resolve().parent.parent / "data" / "synthea" / "fixture_all_types.json"
EXPECTED_RECORDS = 13  # 1 patient + 1 enc + 1 cond + 1 obs + 1 med + 1 proc + 1 dr + 1 alg + 5 raw


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=15.0) as client:
        with FIXTURE.open("rb") as fh:
            resp = client.post(
                "/api/v1/bundles/upload",
                files={"file": (FIXTURE.name, fh, "application/json")},
            )
        resp.raise_for_status()
        run_id = resp.json()["pipeline_run_id"]
        print(f"uploaded all-types fixture -> run_id={run_id}")

        for _ in range(40):
            run = client.get(f"/api/v1/bundles/{run_id}").json()
            if run["status"] in ("completed", "failed"):
                break
            time.sleep(0.5)

        print(f"status={run['status']} records={run['record_count']} errors={run['error_count']}")
        if run["status"] != "completed":
            print("FAIL: pipeline did not complete")
            return 1
        if run["record_count"] != EXPECTED_RECORDS:
            print(f"FAIL: expected {EXPECTED_RECORDS} records, got {run['record_count']}")
            return 1
        if run["error_count"] != 0:
            print("FAIL: parse errors present")
            return 1

        patients = client.get("/api/v1/patients").json()
        if not any(p["family_name"] == "Bryant" for p in patients):
            print("FAIL: Kobe not found in registry")
            return 1

        print("\nPASS: all 13 resource types parsed + persisted end-to-end.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
