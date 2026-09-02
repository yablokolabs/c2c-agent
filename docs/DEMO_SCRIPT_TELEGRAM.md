# Demo script — Telegram

*For a demo filmed as a chat conversation rather than a terminal walkthrough.
The terminal version is [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md); the structure and
timings below match it, so the rest of the video is unchanged.*

**Screen:** the Telegram chat, full frame. A second terminal off-camera, for the
airline's side.

---

## Before you record

```bash
docker compose up -d --build
docker compose --profile telegram up -d bot
docker compose logs bot          # -> C2C is listening on Telegram
```

Confirm the model is reachable **before** anything else — on a fresh VM this is
the step that fails:

```bash
docker compose exec api sh -c 'cd /tmp && claude -p "Reply with exactly: PONG" \
  --model claude-haiku-4-5-20251001 --system-prompt "Terse." \
  --strict-mcp-config --mcp-config "{\"mcpServers\":{}}" \
  --setting-sources "" --allowed-tools "" --max-turns 1'
```

Clear the chat history so `/start` reads as a first contact.

> **The assessment takes three to four minutes.** You cannot sit through that on
> camera. Either do a full dry run first and film the second pass with cuts, or
> cut away at each wait. Both are honest; the timings below assume cuts.

---

## 0:00 — The problem (35s)

Same as the terminal script. Talk over the empty chat.

## 0:35 — The baseline (15s)

Show `prompts/baseline_v2.md` briefly, or say it over the chat:

> "The reasonable first thing is one prompt — whole policy, whole case file, ask
> for the answer. Same model, same schema as what you're about to see. It just
> has no tools, doesn't check itself, and forgets everything when the call ends."

## 0:50 — First contact (25s)

Send **`/start`**.

> "It introduces itself, says what it does, and — the part I care about — says
> what it won't do. It won't guess a detail I didn't give it, and it won't send
> anything to an airline without asking me."

## 1:15 — Describe the disruption (35s)

Type it as a passenger would, not as a form:

```
Flight IN300 from Helsinki to Istanbul on 23 June was cancelled.
Booking IN5540, Y. Tanaka. They told me on the 22nd at 23:40.
They're blaming a bird strike from the day before and say they owe me nothing.
```

> "No form, no fields. It comes back with a case reference I can quote, and tells
> me it's reading the documents. Nothing has been sent anywhere yet."

**Cut here.** The assessment runs three to four minutes.

## 1:50 — What comes back (60s)

The approval message arrives: amount, reasoning, clauses, **Approve / Reject**.

> "A bird strike genuinely *is* an extraordinary circumstance — under this policy
> the airline owes nothing for one. So the obvious answer is no claim.
>
> Look at what it actually found. The bird strike ended 01:10 on the 22nd. My
> flight was due out 17:10 on the 23rd. Forty hours. The policy says an
> extraordinary cause reverts to the airline's responsibility past twelve hours
> if they could have recovered — and their own log says they had two spare
> aircraft sitting at Helsinki and used neither.
>
> The excuse was real. It expired. 420 units.
>
> And now it stops and asks me. That's the whole interaction — I'm not managing a
> case, I'm answering a question."

## 2:50 — Approve, and the weeks pass (35s)

Tap **Approve**. "Filed" arrives with the 56-day clock.

Off-camera terminal:

```bash
docker compose exec api python -m c2c.tools.carrier
```

> "Filed. Now in real life this is where it goes quiet for six weeks — and where
> most valid claims die, because nobody is still holding them.
>
> Here's the airline coming back. Refused, citing the bird strike again."

The next message arrives: the agent has re-read the refusal and proposes a
challenge.

> "It re-read their refusal against the same log, held its position, and it's
> asking me again. Nothing goes out unless I say so."

Tap **Approve**.

## 3:25 — Where it breaks, and holds (50s)

Cut to a terminal — a **pre-shot clip** filmed during a dry run. The
durability suite hosts and kills its own SDK service and force-registers it,
so in this dockerized stack it runs in a throwaway container with the
long-running workflow stopped first (the §6 recipe). Never run it live
mid-take, and never the host form (`make failure-tests`) or a bare
`docker compose exec` — against this stack that kills or snubs the live
workflow service (F-024). The terminal script's `make failure-tests` form is
only accurate against the host topology (`make up`).

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

docker compose start workflow
# restore the registration the throwaway container clobbered (REPRODUCTION_GUIDE §6):
curl -s localhost:9070/deployments | grep -o '"uri":"[^"]*"'    # find the stale uri
curl -X DELETE "http://localhost:9070/deployments/<STALE_ID>?force=true"
curl -X POST http://localhost:9070/deployments -H 'content-type: application/json' \
  -d '{"uri":"http://workflow:9095","force":true}'
```

Expected: `6/6` scenarios, `duplicate consequential acts 0`. Read the raw
numbers off the newest `evaluation/results/durability--*.json` — D01
`calls_that_reached_the_carrier == 4`, D06 `2 / 1`, D05 `0` — while you
narrate.

> "Six failure scenarios. The one that matters is D06 — SIGKILL the worker in the
> window around the submission. The carrier received **two** attempts and **one**
> claim landed. The retry genuinely happened; the idempotency key absorbed it.
>
> And D05: when a human refuses, the carrier is called **zero** times. Not once
> and rolled back — never called."

## 4:15 — Results and the honest bit (45s)

Same as the terminal script — `make compare`, the changelog, NanoClaw removed,
and the tools that mostly went unused.

## 5:00 — Hot take (20s)

Unchanged.

---

## Driving the airline, off camera

| What you want | Command |
|---|---|
| Airline refuses | `docker compose exec api python -m c2c.tools.carrier` |
| Airline offers too little | `docker compose exec api python -m c2c.tools.carrier --settle 210` |
| Airline answers the challenge | `docker compose exec api python -m c2c.tools.carrier --after-challenge` |

All three target the most recently opened live case, so you never have to read a
reference off your phone mid-take.

The `--settle 210` variant is worth knowing: the agent compares the offer against
the full entitlement under S9.4 and tells the passenger it is **210 short** and
that it would push back. That is a strong beat if you have time for it.

The `--after-challenge` variant produces the challenge-outcome message (F-025):
if the airline holds the refusal the passenger is told the case is resolved on
C2C's side with everything preserved; if the reply is a settlement, the amount
is named.

## If something stalls

| Symptom | Cause |
|---|---|
| PONG check hangs with no output | the container has no outbound network (see below) |
| No reply to `/start` | bot not running: `docker compose --profile telegram up -d bot` |
| Case opens, then nothing | assessment takes 3-4 min. `docker compose logs api` to watch. |
| "Filed" then silence | expected — the airline has not replied. Run the carrier command. |
| Two bots replying | Telegram allows one poller per token. Stop the other. |

### The PONG check hangs (no output, no error)

The PONG check above is the model-reachability gate: if it hangs, nothing that
needs a model will work, so fix it before recording. First confirm the
container itself cannot reach the internet:

```bash
docker compose exec api sh -c 'curl -sS -o /dev/null -w "%{http_code}\n" https://api.anthropic.com'
```

A hang here (rather than an error) means outbound traffic from the compose
network is being dropped by the host. A known cause is a stale **legacy
iptables** ruleset left over from an older Docker install: its `FORWARD` chain
has `policy DROP` and only knows about the default `docker0` bridge, so the
compose bridge (`br-...`) is silently dropped and the container never reaches
NAT. Docker's own nftables rules may look fine while the legacy ruleset does
the dropping. Diagnose with:

```bash
sudo iptables-legacy -L FORWARD -n -v   # policy DROP, no rule for your compose bridge
```

Fix — the bridge name and subnet are derived from the running stack, so the
same commands work for any judge's machine:

```bash
CONTAINER=$(docker compose ps -q api)
NETWORK=$(docker inspect "$CONTAINER" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')
BRIDGE=br-$(docker network inspect "$NETWORK" --format '{{.Id}}' | cut -c1-12)
SUBNET=$(docker network inspect "$NETWORK" --format '{{(index .IPAM.Config 0).Subnet}}')
sudo iptables-legacy -I DOCKER-FORWARD -i "$BRIDGE" -j ACCEPT
sudo iptables-legacy -I DOCKER-CT -o "$BRIDGE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
sudo iptables-legacy -t nat -A POSTROUTING -s "$SUBNET" ! -o "$BRIDGE" -j MASQUERADE
```

Re-run the PONG check; it should return `PONG`. These rules are runtime-only
and do not survive a reboot — re-apply them if the hang returns on a fresh
boot.
