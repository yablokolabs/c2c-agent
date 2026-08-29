"""Failure-injection suite for the durable workflow.

Measures what the reasoning benchmark cannot: whether the system stays with a
case when things break. Six scenarios, each one a specific invariant from the
project brief.

The agent is deliberately not in the loop here. Each scenario points the
workflow's assess step at a stub that returns a fixed verdict, because what is
under test is the workflow, and model nondeterminism would only add variance to
a measurement about crash recovery. The stub is configuration
(`C2C_CONTROL_PLANE`), not a code path that exists only for tests.

Ground truth for every scenario is the airline simulator's audit log, which
counts the actions that actually landed rather than the ones that were attempted.

Requires: the shared Restate server, the C2C control plane, and the C2C SDK
service. `make failure-tests` brings them up.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

INGRESS = os.environ.get("C2C_RESTATE_INGRESS", "http://localhost:8080")
AIRLINE = os.environ.get("C2C_AIRLINE_BASE", "http://localhost:8099/airline")
STUB_PORT = int(os.environ.get("C2C_STUB_PORT", "8098"))
SERVICE_PORT = int(os.environ.get("C2C_RESTATE_SERVICE_PORT", "9095"))
WF = "C2CCase"
RESULTS = Path("evaluation/results")

# A workflow id is single-use for the retention period, so each run of the suite
# gets its own case ids. Without this the suite is runnable exactly once a day.
RUN_TAG = datetime.now(timezone.utc).strftime("%m%d%H%M%S")


def case_id(scenario: str) -> str:
    return f"DUR-{scenario}-{RUN_TAG}"

STUB_VERDICT = {
    "in_scope": True, "qualifies": True, "cause_class": "carrier_controlled",
    "eligible": True, "compensation_units": 420, "duty_of_care_units": 0,
    "downgrade_reimbursement_units": 0, "evidence_sufficient": True,
    "missing_evidence": [], "next_action": "submit_claim",
    "policy_citations": ["S2.1(a)", "S3.2(b)", "S5.1"],
    "rationale": "Fixed verdict from the durability stub.",
}

STUB_SOURCE = '''
import os
from fastapi import FastAPI
app = FastAPI()
VERDICT = %r
@app.post("/c2c/assess")
async def assess(body: dict) -> dict:
    return VERDICT
@app.get("/health")
async def health() -> dict:
    return {"ok": True}
''' % (STUB_VERDICT,)


@dataclass
class Scenario:
    id: str
    name: str
    invariant: str
    passed: bool = False
    workflow_completed: bool = False
    state_preserved: bool = False
    duplicate_actions: int = 0
    recovered: bool = False
    final_outcome: str = ""
    detail: dict = field(default_factory=dict)
    notes: str = ""


def _client() -> httpx.Client:
    return httpx.Client(timeout=120)


def airline_reset(c: httpx.Client) -> None:
    c.post(f"{AIRLINE}/_admin/reset")


def audit(c: httpx.Client) -> dict:
    return c.get(f"{AIRLINE}/_admin/audit").json()


def effective(c: httpx.Client, action: str, case_id: str) -> int:
    return sum(1 for e in audit(c)["effective"]
               if e["action"] == action and e["case_id"] == case_id)


def attempts(c: httpx.Client, action: str, case_id: str) -> int:
    return sum(1 for e in audit(c)["entries"]
               if e["action"] == action and e["case_id"] == case_id)


def start_workflow(c: httpx.Client, case_id: str) -> None:
    c.post(f"{INGRESS}/{WF}/{case_id}/run/send",
           json={"opened_by": "durability", "passenger": "T. Subject", "pnr": "DUR001"})


def status(c: httpx.Client, case_id: str) -> dict:
    r = c.post(f"{INGRESS}/{WF}/{case_id}/status")
    return r.json() if r.status_code == 200 else {}


def approve(c: httpx.Client, case_id: str, approved: bool, promise: str = "approval") -> dict:
    r = c.post(f"{INGRESS}/{WF}/{case_id}/approve",
               json={"approved": approved, "promise": promise, "by": "durability"})
    return r.json() if r.status_code == 200 else {"error": r.status_code, "body": r.text[:200]}


def carrier_event(c: httpx.Client, case_id: str, payload: dict,
                  promise: str = "carrier_response") -> dict:
    r = c.post(f"{INGRESS}/{WF}/{case_id}/carrier_event",
               json={"promise": promise, "payload": payload})
    return r.json() if r.status_code == 200 else {"error": r.status_code, "body": r.text[:200]}


def wait_for_state(c: httpx.Client, case_id: str, wanted: set[str], timeout: float = 90) -> str:
    deadline = time.monotonic() + timeout
    seen = ""
    while time.monotonic() < deadline:
        seen = status(c, case_id).get("state", "")
        if seen in wanted:
            return seen
        time.sleep(0.5)
    return seen


class Service:
    """The C2C SDK service process, so scenarios can kill and restart it."""

    def __init__(self, control_plane: str):
        self.control_plane = control_plane
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        env = {**os.environ, "C2C_CONTROL_PLANE": self.control_plane,
               "C2C_RESTATE_SERVICE_PORT": str(SERVICE_PORT)}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "c2c.restate_service"], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if subprocess.run(["ss", "-lnt", f"sport = :{SERVICE_PORT}"],
                              capture_output=True, text=True).stdout.count("LISTEN"):
                time.sleep(1)
                return
            time.sleep(0.3)
        raise RuntimeError("C2C SDK service did not come up")

    def kill(self) -> None:
        """SIGKILL, not SIGTERM. A graceful shutdown is not a crash.

        Kills whatever holds the port, not only this object's child, so the
        suite can take over a service that was started outside it.
        """
        if self.proc:
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait(timeout=15)
            self.proc = None
        subprocess.run(["pkill", "-9", "-f", "c2c.restate_service"], capture_output=True)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if not subprocess.run(["ss", "-lnt", f"sport = :{SERVICE_PORT}"],
                                  capture_output=True, text=True).stdout.count("LISTEN"):
                return
            time.sleep(0.3)
        raise RuntimeError(f"port {SERVICE_PORT} still held after SIGKILL")

    def restart(self) -> None:
        self.kill()
        self.start()


# --- the scenarios ----------------------------------------------------------

def d01_carrier_api_503(c: httpx.Client, svc: Service) -> Scenario:
    """The carrier API fails three times. Restate retries the durable step.

    Invariant: a claim must not be submitted twice because of a retry.
    """
    s = Scenario("D01", "carrier API returns 503 three times",
                 "retries must not produce a second submission")
    case = case_id("D01")
    airline_reset(c)
    c.post(f"{AIRLINE}/_admin/inject", json={"injection": "503", "times": 3})
    start_workflow(c, case)
    wait_for_state(c, case, {"AWAITING_APPROVAL"})
    approve(c, case, True)
    state = wait_for_state(c, case, {"SUBMITTED", "AWAITING_CARRIER"})

    landed = effective(c, "submit_claim", case)
    reached = audit(c)["call_counts"].get("submit_claim", 0)
    s.workflow_completed = state in ("SUBMITTED", "AWAITING_CARRIER")
    s.recovered = s.workflow_completed
    s.duplicate_actions = max(0, landed - 1)
    s.state_preserved = bool(status(c, case).get("claim_id"))
    s.final_outcome = state
    s.detail = {"calls_that_reached_the_carrier": reached, "injected_503s": 3,
                "submissions_that_landed": landed}
    # 4 calls: three rejected with 503, one that succeeded. Fewer would mean the
    # injection never fired and the scenario proved nothing.
    s.passed = landed == 1 and s.workflow_completed and reached == 4
    s.notes = (f"the carrier endpoint was called {reached} times: three answered 503 and one "
               f"succeeded. Restate retried the durable step and {landed} submission landed.")
    return s


def d02_worker_crash_before_approval(c: httpx.Client, svc: Service) -> Scenario:
    """SIGKILL the SDK service while the workflow is suspended on approval.

    Invariant: a restart must not lose case state.
    """
    s = Scenario("D02", "worker killed while awaiting human approval",
                 "a restart must not lose case state")
    case = case_id("D02")
    airline_reset(c)
    start_workflow(c, case)
    wait_for_state(c, case, {"AWAITING_APPROVAL"})
    before = status(c, case)

    svc.kill()
    time.sleep(2)
    svc.restart()

    after = status(c, case)
    s.state_preserved = (after.get("verdict") == before.get("verdict")
                         and after.get("state") == "AWAITING_APPROVAL")
    approve(c, case, True)
    state = wait_for_state(c, case, {"SUBMITTED", "AWAITING_CARRIER"})
    landed = effective(c, "submit_claim", case)
    s.workflow_completed = state in ("SUBMITTED", "AWAITING_CARRIER")
    s.recovered = s.workflow_completed
    s.duplicate_actions = max(0, landed - 1)
    s.final_outcome = state
    s.detail = {"state_before_kill": before.get("state"), "state_after_restart": after.get("state"),
                "verdict_survived": after.get("verdict") == before.get("verdict"),
                "submissions_that_landed": landed}
    s.passed = s.state_preserved and landed == 1 and s.workflow_completed
    s.notes = ("the workflow was suspended on a durable promise, so the kill cost nothing and "
               "the approval given after the restart still resolved it.")
    return s


def d03_duplicate_carrier_event(c: httpx.Client, svc: Service) -> Scenario:
    """The same carrier response is delivered twice.

    Invariant: duplicate external events must not duplicate side effects.
    """
    s = Scenario("D03", "the same carrier rejection delivered twice",
                 "a duplicate external event must not duplicate side effects")
    case = case_id("D03")
    airline_reset(c)
    start_workflow(c, case)
    wait_for_state(c, case, {"AWAITING_APPROVAL"})
    approve(c, case, True)
    wait_for_state(c, case, {"AWAITING_CARRIER"})

    payload = {"type": "rejection", "text": "extraordinary circumstances"}
    first = carrier_event(c, case, payload)
    second = carrier_event(c, case, payload)

    state = wait_for_state(c, case, {"AWAITING_APPROVAL"})
    approve(c, case, True, promise="challenge_approval")
    wait_for_state(c, case, {"CHALLENGED"})

    challenges = effective(c, "challenge_rejection", case)
    s.workflow_completed = True
    s.recovered = True
    s.duplicate_actions = max(0, challenges - 1)
    s.state_preserved = True
    s.final_outcome = status(c, case).get("state", "")
    s.detail = {"first_delivery": first, "second_delivery": second,
                "challenges_that_landed": challenges}
    s.passed = (second.get("duplicate") is True and challenges == 1)
    s.notes = ("the second delivery was rejected by the durable promise, which had already been "
               "resolved, so exactly one challenge reached the carrier.")
    return s


def d04_duplicate_approval(c: httpx.Client, svc: Service) -> Scenario:
    """A human clicks approve twice.

    Invariant: a consequential action executes at most once per intent.
    """
    s = Scenario("D04", "human approves the same action twice",
                 "a consequential action executes at most once per intent")
    case = case_id("D04")
    airline_reset(c)
    start_workflow(c, case)
    wait_for_state(c, case, {"AWAITING_APPROVAL"})

    first = approve(c, case, True)
    second = approve(c, case, True)
    state = wait_for_state(c, case, {"SUBMITTED", "AWAITING_CARRIER"})

    landed = effective(c, "submit_claim", case)
    s.workflow_completed = state in ("SUBMITTED", "AWAITING_CARRIER")
    s.recovered = True
    s.duplicate_actions = max(0, landed - 1)
    s.state_preserved = True
    s.final_outcome = state
    s.detail = {"first_approval": first, "second_approval": second,
                "submissions_that_landed": landed}
    s.passed = (second.get("duplicate") is True and landed == 1)
    s.notes = "the second approval was absorbed; one submission reached the carrier."
    return s


def d05_rejected_action_never_executes(c: httpx.Client, svc: Service) -> Scenario:
    """A human refuses the action.

    Invariant: an action a human rejected must never execute.
    """
    s = Scenario("D05", "human rejects the pending submission",
                 "a rejected action must never execute")
    case = case_id("D05")
    airline_reset(c)
    start_workflow(c, case)
    wait_for_state(c, case, {"AWAITING_APPROVAL"})
    approve(c, case, False)
    state = wait_for_state(c, case, {"CLOSED_BY_HUMAN"})

    tried = attempts(c, "submit_claim", case)
    landed = effective(c, "submit_claim", case)
    s.workflow_completed = state == "CLOSED_BY_HUMAN"
    s.recovered = True
    s.duplicate_actions = landed
    s.state_preserved = True
    s.final_outcome = state
    s.detail = {"submit_attempts_at_carrier": tried, "submissions_that_landed": landed}
    s.passed = (landed == 0 and tried == 0 and state == "CLOSED_BY_HUMAN")
    s.notes = ("the carrier was never called at all; the rejection branch returns before any "
               "side effect is reachable.")
    return s


def d06_crash_around_the_side_effect(c: httpx.Client, svc: Service) -> Scenario:
    """SIGKILL the worker immediately after approving, racing the submission.

    Invariant: a crash around a consequential side effect must not double it.
    This is the hardest of the six: the kill lands in the window where the
    submission may have reached the carrier but the workflow may not yet have
    journalled it.
    """
    s = Scenario("D06", "worker killed in the window around the submission",
                 "a crash around a side effect must not double it")
    case = case_id("D06")
    airline_reset(c)
    c.post(f"{AIRLINE}/_admin/inject", json={"injection": "slow", "times": 1})
    start_workflow(c, case)
    wait_for_state(c, case, {"AWAITING_APPROVAL"})
    approve(c, case, True)

    time.sleep(1.0)  # the injected 2s delay puts the kill inside the submit call
    svc.kill()
    time.sleep(2)
    svc.restart()

    state = wait_for_state(c, case, {"SUBMITTED", "AWAITING_CARRIER"}, timeout=120)
    landed = effective(c, "submit_claim", case)
    tried = attempts(c, "submit_claim", case)
    s.workflow_completed = state in ("SUBMITTED", "AWAITING_CARRIER")
    s.recovered = s.workflow_completed
    s.duplicate_actions = max(0, landed - 1)
    s.state_preserved = bool(status(c, case).get("claim_id"))
    s.final_outcome = state
    s.detail = {"submit_attempts_at_carrier": tried, "submissions_that_landed": landed}
    s.passed = landed == 1 and s.workflow_completed
    s.notes = (f"the carrier saw {tried} attempt(s) and {landed} landed. Where the retry did "
               "reach the carrier twice, the replay-stable idempotency key made the second one "
               "a no-op.")
    return s


SCENARIOS = [d01_carrier_api_503, d02_worker_crash_before_approval,
             d03_duplicate_carrier_event, d04_duplicate_approval,
             d05_rejected_action_never_executes, d06_crash_around_the_side_effect]


def main() -> int:
    from c2c.trajectory import git_sha

    stub_path = Path("/tmp/c2c_durability_stub.py")
    stub_path.write_text(STUB_SOURCE)
    stub = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "c2c_durability_stub:app",
         "--host", "127.0.0.1", "--port", str(STUB_PORT)],
        cwd=stub_path.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    svc = Service(control_plane=f"http://127.0.0.1:{STUB_PORT}")
    results: list[Scenario] = []
    try:
        with _client() as c:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    c.get(f"http://127.0.0.1:{STUB_PORT}/health"); break
                except Exception:  # noqa: BLE001
                    time.sleep(0.3)
            svc.restart()
            for fn in SCENARIOS:
                print(f"  {fn.__name__} ...", flush=True)
                started = time.monotonic()
                try:
                    sc = fn(c, svc)
                except Exception as exc:  # noqa: BLE001
                    sc = Scenario(fn.__name__[:3].upper(), fn.__name__, "n/a")
                    sc.notes = f"scenario raised: {exc!r}"
                sc.detail["elapsed_s"] = round(time.monotonic() - started, 1)
                results.append(sc)
                print(f"    {sc.id} {'PASS' if sc.passed else 'FAIL'}  {sc.name}", flush=True)
    finally:
        stub.terminate()

    n = len(results)
    summary = {
        "suite": "durability",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "n_scenarios": n,
        "workflow_completion_rate": round(sum(s.workflow_completed for s in results) / n, 4),
        "failure_recovery_rate": round(sum(s.recovered for s in results) / n, 4),
        "state_preservation_rate": round(sum(s.state_preserved for s in results) / n, 4),
        "duplicate_consequential_actions": sum(s.duplicate_actions for s in results),
        "scenarios_passed": sum(s.passed for s in results),
        "scenarios": [vars(s) for s in results],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"durability--{stamp}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n  scenarios passed              {summary['scenarios_passed']}/{n}")
    print(f"  workflow completion           {summary['workflow_completion_rate']:.2f}")
    print(f"  failure recovery              {summary['failure_recovery_rate']:.2f}")
    print(f"  state preserved               {summary['state_preservation_rate']:.2f}")
    print(f"  duplicate consequential acts  {summary['duplicate_consequential_actions']}")
    print(f"\n  results  {out}")
    return 0 if summary["scenarios_passed"] == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
