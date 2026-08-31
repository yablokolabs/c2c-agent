"""Assert the shared Restate server is intact.

The Restate server C2C registers with was already running and already hosting
an unrelated project's services. This records those services on first run and
checks they are still there on every later run, so any collateral damage from
C2C would be caught rather than assumed away.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ADMIN = os.environ.get("C2C_RESTATE_ADMIN", "http://localhost:9070")
BASELINE = Path("evaluation/restate-tenants-baseline.json")
OURS_PREFIX = "C2C"


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{ADMIN}{path}", timeout=10) as r:
        return json.loads(r.read())


def main() -> int:
    version = get("/version")
    services = {s["name"] for s in get("/services")["services"]}
    theirs = sorted(s for s in services if not s.startswith(OURS_PREFIX))
    ours = sorted(s for s in services if s.startswith(OURS_PREFIX))

    print(f"Restate {version['version']} at {ADMIN}")
    print(f"  pre-existing services : {', '.join(theirs) or 'none'}")
    print(f"  C2C services          : {', '.join(ours) or 'none (not registered)'}")

    # Keyed by admin endpoint. Tenants are a property of one server, and a
    # single global record false-alarms the moment you point this at another —
    # a containerised Restate legitimately has none of the host's tenants.
    record = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    if "pre_existing_services" in record:  # migrate the old single-server format
        record = {os.environ.get("C2C_RESTATE_ADMIN_LEGACY", "http://localhost:9070"): record}

    if ADMIN not in record:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        record[ADMIN] = {"restate_version": version["version"],
                         "pre_existing_services": theirs}
        BASELINE.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(f"\n  first run against {ADMIN} — recorded its tenants to {BASELINE}")
        return 0

    expected = record[ADMIN]["pre_existing_services"]
    missing = [s for s in expected if s not in services]
    if missing:
        print(f"\n  FAIL: pre-existing services are gone: {', '.join(missing)}")
        print("  C2C must never remove a deployment it did not create.")
        return 1
    if not expected:
        print(f"\n  OK: {ADMIN} had no other tenants to protect")
        return 0
    print(f"\n  OK: all {len(expected)} pre-existing services still registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
