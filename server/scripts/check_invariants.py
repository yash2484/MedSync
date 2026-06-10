"""Ad-hoc checks for Increment 1 invariants: idempotency + WebSocket status."""

import threading
import time

import httpx
from websockets.sync.client import connect

BASE = "http://localhost:8000"


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=10)

    # --- Idempotency: re-upload the diabetes fixture; Shaq must not duplicate ---
    before = c.get("/api/v1/patients").json()
    with open("data/synthea/fixture_diabetes_patient.json", "rb") as f:
        c.post("/api/v1/bundles/upload", files={"file": ("d.json", f, "application/json")})
    time.sleep(2)
    after = c.get("/api/v1/patients").json()
    shaqs = [p for p in after if p["family_name"] == "O'Neal"]
    print(f"idempotency: patients before={len(before)} after re-upload={len(after)} "
          f"| Shaq rows={len(shaqs)} (expect 1)")

    # --- WebSocket: subscribe, then upload Lebron, capture stage events ---
    msgs: list[str] = []

    # Pre-create a run by uploading, then immediately connect. Parse is fast, so
    # we may catch 0-2 events; this confirms the WS endpoint accepts + relays.
    with open("data/synthea/fixture_routine_patient.json", "rb") as f:
        rid = c.post("/api/v1/bundles/upload",
                     files={"file": ("l.json", f, "application/json")}).json()["pipeline_run_id"]

    def listen():
        try:
            with connect(f"ws://localhost:8000/api/v1/bundles/{rid}/status") as ws:
                ws.recv(timeout=4)
                while True:
                    msgs.append(ws.recv(timeout=4))
        except Exception:
            pass

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(4)

    allp = c.get("/api/v1/patients").json()
    print(f"total patients now={len(allp)}: "
          f"{[p['given_name'] + ' ' + p['family_name'] for p in allp]}")
    print(f"ws messages captured for run {rid}: {msgs}")


if __name__ == "__main__":
    main()
