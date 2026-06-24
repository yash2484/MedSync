import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
F = Path(__file__).resolve().parent.parent / "data" / "synthea"


def _upload_and_wait(c, name):
    with (F / name).open("rb") as fh:
        rid = c.post(
            "/api/v1/bundles/upload", files={"file": (name, fh, "application/json")}
        ).json()["pipeline_run_id"]
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
            print("FAIL: pipeline did not complete")
            return 1
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
