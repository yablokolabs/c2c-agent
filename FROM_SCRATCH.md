# From scratch, on a clean machine

Every command below was run on a fresh `git clone` into an empty directory. The
outputs are what actually came back, not what should have.

**Verified on:** commit `bbb7429`, Ubuntu 24.04, Docker 29.1.3.

---

## What you need

**Docker, and nothing else.** No Python, no Restate, no database.

Model access, one of:

- an `ANTHROPIC_API_KEY`, **or**
- an existing Claude Code login on the machine — the container mounts and reuses
  it, no key required.

Neither is needed to verify the project works. The test suite and the durability
suite make **zero** model calls.

---

## 1. Clone

```bash
git clone https://github.com/yablokolabs/c2c-agent.git
cd c2c-agent
```

You get no `.env` and no live case data — both are gitignored. Only
`.env.example`.

## 2. Configure

```bash
cp .env.example .env
```

Then either put a key in it:

```
ANTHROPIC_API_KEY=sk-ant-...
```

…or leave it blank and rely on the mounted Claude Code login, which
`docker-compose.yml` wires up by default.

Telegram is optional and can stay blank. Everything works over HTTP without it.

> Running this alongside another C2C stack? Add distinct ports:
> `C2C_RESTATE_ADMIN_PORT=9270`, `C2C_RESTATE_INGRESS_PORT=8280`,
> `C2C_API_PORT=8299`.

## 3. Bring it up

```bash
docker compose up -d --build
```

First build is a few minutes — it installs Python deps, Node, and the Claude CLI.

**Expected:**

```
 Container c2c-agent-restate-1   Healthy
 Container c2c-agent-api-1       Healthy
 Container c2c-agent-workflow-1  Started
 Container c2c-agent-register-1  Started
```

`register` exits `0` once it has registered the workflow. That is success, not a
crash.

## 4. Check it

```bash
docker compose logs register     # -> registered C2CCase
curl localhost:8099/c2c/health   # -> {"ok":true,"cases":28,...}
curl localhost:9070/services     # -> C2CCase
```

Confirm the container can reach a model:

```bash
docker compose exec api sh -c 'cd /tmp && claude -p "Reply with exactly: PONG" \
  --model claude-haiku-4-5-20251001 --system-prompt "Terse." \
  --strict-mcp-config --mcp-config "{\"mcpServers\":{}}" \
  --setting-sources "" --allowed-tools "" --max-turns 1'
```

**Expected:** `PONG`. If it fails, you need an `ANTHROPIC_API_KEY` in `.env`.

## 5. The test suite — no model calls, no services

```bash
docker compose exec api python -m pytest tests/ -q
```

**Expected:** `170 passed, 1 skipped` in about a second.

## 6. Durability — 6/6, no model calls, ~30 seconds

The suite hosts and kills its own SDK service, so it runs in its own container.
Stop the long-running one first so they do not fight over the registration:

```bash
docker compose stop workflow

docker compose run --rm \
  -e C2C_RESTATE_INGRESS=http://restate:8080 \
  -e C2C_AIRLINE_BASE=http://api:8099/airline \
  -e C2C_AIRLINE=http://api:8099/airline \
  -e C2C_RESTATE_ADMIN=http://restate:9070 \
  api sh -c '
    H=$(hostname -i | awk "{print \$1}")
    python -m c2c.restate_service > /tmp/svc.log 2>&1 &
    for i in $(seq 1 40); do curl -s -o /dev/null http://localhost:9095 && break; sleep 1; done
    curl -fs -X POST http://restate:9070/deployments -H "content-type: application/json" \
      -d "{\"uri\":\"http://$H:9095\",\"force\":true}" >/dev/null
    sleep 2; python -m c2c.eval.durability'
```

**Expected:**

```
  scenarios passed              6/6
  workflow completion           1.00
  failure recovery              1.00
  state preserved               1.00
  duplicate consequential acts  0
```

Then check the three numbers that make it evidence rather than a green tick, in
the newest `evaluation/results/durability--*.json`:

| Scenario | Field | Expected |
|---|---|---|
| D01 | `calls_that_reached_the_carrier` | **4** — three 503s and one success |
| D06 | `submit_attempts_at_carrier` / `submissions_that_landed` | **2 / 1** |
| D05 | `submit_attempts_at_carrier` | **0** |

If D06 shows 1 attempt, the `SIGKILL` missed its window and the scenario proved
nothing — re-run it.

**Afterwards, restore the long-running workflow service.** The throwaway
container registered its own address, and Restate is now routing to a container
that no longer exists:

```bash
docker compose start workflow
curl -s localhost:9070/deployments | grep -o '"uri":"[^"]*"'   # find the stale one
curl -X DELETE "http://localhost:9070/deployments/<STALE_ID>?force=true"
curl -X POST http://localhost:9070/deployments -H 'content-type: application/json' \
  -d '{"uri":"http://workflow:9095","force":true}'
```

Skipping this leaves every later call timing out, with the containers all
looking healthy.

## 7. One case, end to end

```bash
docker compose exec api python -m c2c.tools.demo
```

**This takes 7 to 16 minutes** and makes about ten model calls. A single
assessment is 3.5 minutes at the median across 34 measured runs, and the demo
does two.

Eight steps: reset, open, assess and stop for approval, approve, the carrier's
rejection arrives, approve the challenge, the documents the passenger receives,
and the audit of what actually landed.

**Expected at the end:**

```
    1  submit_claim         R12   key=…
    2  challenge_rejection  R12   key=…
  2 action(s) attempted, 2 landed.
  Duplicates absorbed: 0
```

Final state `CHALLENGED`, 420 units, citing S3.6 and S9.1(a).

## 8. The headline benchmark — costs real money

```bash
docker compose exec api python -m c2c.eval.run --system baseline --stage baseline-check
```

~28 model calls, ~15 minutes, ~$1.40. The full agent is ~102 calls and ~$3.80.
`REPRODUCE_AND_RECORD.md` §3 has the whole chain including the merge step, and
§6 covers the throughput ceiling you will probably hit on the agent run.

Committed results are in `evaluation/results/`; you do not have to re-run them to
read them.

## 9. Tear down

```bash
docker compose down -v
```

Removes the containers and the Restate volume. Nothing is left behind, and no
Restate you already had was touched — this stack runs its own.

---

## What was actually verified this way

| Step | Result |
|---|---|
| clone, no secrets in the tree | ✅ no `.env`, no live cases |
| `pytest` from a clean clone | ✅ **170 passed, 1 skipped** |
| `docker compose up --build` | ✅ all four containers, `registered C2CCase` |
| model reachable with no API key | ✅ `PONG` via the mounted login |
| durability suite in the clean stack | ✅ **6/6, 0 duplicate actions** |

The one thing this exercise found: `hypercorn` and `restate-sdk` were installed
by hand during development and were missing from `pyproject.toml`, so a clean
clone could not start the workflow service at all. It is fixed, and it is the
argument for doing this from an empty directory rather than trusting the machine
you built it on.
