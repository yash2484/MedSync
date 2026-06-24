import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
F = Path(__file__).resolve().parent.parent / "data" / "synthea"
FIX = (
    "fixture_all_types.json" if (F / "fixture_all_types.json").exists() else "fixture_diabetes_patient.json"
)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=20) as c:
        with (F / FIX).open("rb") as fh:
            rid = c.post(
                "/api/v1/bundles/upload", files={"file": (FIX, fh, "application/json")}
            ).json()["pipeline_run_id"]
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
