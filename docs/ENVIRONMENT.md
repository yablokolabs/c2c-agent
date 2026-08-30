# Environment Findings

Recorded before any C2C code was written. Everything below was observed on the
build host, not assumed.

## Host

| Item | Value |
|---|---|
| OS | Ubuntu 24.04.4 LTS (`Linux 6.17.0-1022-azure`, x86_64) |
| Machine | Azure VM |
| Python | 3.12.3 |
| uv | 0.12.5 |
| Docker | 29.1.3 |
| Claude Code CLI | 2.1.250 |
| GitHub CLI | authenticated as `yablokolabs` |

## Restate — pre-existing, shared, NOT owned by C2C

A Restate server was already running before this project started. It is
**shared with an unrelated project** and must not be reinstalled, restarted or
replaced.

```
$ ps -o pid,ppid,cmd -p 1064
1064  963  .../@restatedev/restate-server-linux-x64/bin/restate-server
```

Launched by `~/.local/lib/node_modules/@restatedev/restate-server` (npm
distribution, not Docker). Supervised by pid 963.

```
$ curl -s http://localhost:9070/version
{"version":"1.7.7","min_admin_api_version":2,"max_admin_api_version":4,
 "ingress_endpoint":"http://10.0.0.4:8080/"}
```

### Ports — 9070 is the admin API, not the ingress

This matters: the project instructions warned against assuming 9070 is the
right endpoint for every interaction. It is not.

| Port | Role | Used by C2C for |
|---|---|---|
| 9070 | Admin API | registering the C2C service deployment, introspection |
| 8080 | Ingress | invoking C2C workflows, sending external events/signals |
| 5122 | Node-to-node / internal | nothing |

### Existing tenants on this server (do not touch)

```
$ curl -s http://localhost:9070/deployments
dp_107G0C9yI4kQffT9stjtiHD  ->  http://localhost:9080/
  sdk: restate-sdk-typescript/1.16.9
  services: Outreach (Workflow), LeadRegistry (VirtualObject), ProspectLoop (Workflow)
```

These belong to `~/yablokolabs/yablokolabs/polaris-restate` and are unrelated to
C2C.

**Consequence for C2C's design:** registering a deployment is *additive* — it
adds services to the shared server and does not disturb existing ones. C2C
therefore:

- runs its own SDK service on **port 9095** and registers it at the admin API
  (9091 was the first choice and is already taken by a minio container),
- namespaces every service it owns with a `C2C` prefix (`C2CCase`, `C2CAirline`),
- never calls `DELETE /deployments/*` for a deployment it did not create,
- tears down only its own deployment in `make down`.

`make restate-check` asserts the pre-existing deployment is still present
before and after C2C runs, so any collateral damage would be caught.

## Model access

Model access is configured via environment variables. C2C abstracts the model
transport behind one interface with two backends (`c2c/llm.py`):

| Backend | When used | Notes |
|---|---|---|
| `api` | `ANTHROPIC_API_KEY` is set, OR both `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` are set | direct Anthropic SDK or local proxy. **The documented path for judges.** |
| `cli` | otherwise | `claude -p --output-format json`, subscription-authenticated |

Measured fixed overhead of the `cli` backend (empty prompt, Haiku 4.5,
MCP and settings sources disabled):

```
input 10  cache_creation 6856  cache_read 12212  output 50   -> $0.0162
```

That ~$0.016 is harness system-prompt overhead paid on every CLI call and is
**not** attributable to C2C's own prompts. Reported token counts in
`evaluation/results/` separate `harness_overhead_tokens` from `task_tokens`
for this reason. The `api` backend does not pay it.

## NanoClaw

Checked out at `~/yablokolabs/nanoclaw` (upstream `github.com/nanocoai/nanoclaw`,
commit `a099c71f`, container claude-code 2.1.238 / agent SDK 0.3.238). Its role
and integration are recorded in `docs/STACK.md`.

## What existed before the competition

Per hackathon ground rule 02:

- The Restate 1.7.7 server, its npm install, and the unrelated `polaris-restate`
  services — **pre-existing, not built for this hackathon.**
- The NanoClaw checkout — **pre-existing third-party open source.**
- The Claude Code CLI and its authentication — **pre-existing.**
- Everything inside this repository — **built for this hackathon.**
