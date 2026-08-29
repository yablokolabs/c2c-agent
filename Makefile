# C2C — Cancellation to Compensation
#
# `make reproduce` produces the headline result from a clean checkout. It needs
# no Restate server, no Docker and no Telegram.
#
# The durability half needs services; `make up` starts them, `make down` stops
# only what C2C started.

PY       := .venv/bin/python
VENV     := .venv
MODEL    ?= claude-haiku-4-5-20251001
RESULTS  := evaluation/results
API_PORT ?= 8099
SVC_PORT ?= 9095
RESTATE_ADMIN ?= http://localhost:9070
RUNDIR   := .run

.DEFAULT_GOAL := help
.PHONY: help setup test baseline evaluate evaluate-tools compare reproduce \
        trajectories restate-check restate-register restate-deregister \
        up down failure-tests demo demo-reset demo-advance demo-approve clean audit

help:  ## show this help
	@grep -hE '^[a-z][a-z-]*:.*?## ' $(MAKEFILE_LIST) | \
	  awk -F':.*?## ' '{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

# --- setup ------------------------------------------------------------------

$(VENV)/bin/python:
	uv venv --python 3.12
	uv pip install -e ".[dev]"

setup: $(VENV)/bin/python  ## create the venv and install C2C
	@$(PY) -c "import c2c; print('c2c', c2c.__version__)"
	@$(PY) -c "from c2c.llm import choose_backend; print('model backend:', choose_backend())"

test: setup  ## run the test suite (no model calls, no services)
	$(PY) -m pytest tests/ -q

clean:  ## remove the venv and caches. Never results or trajectories.
	rm -rf $(VENV) .pytest_cache $(RUNDIR)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

# --- the headline result ----------------------------------------------------

baseline: setup  ## run the baseline over the 28-case benchmark
	$(PY) -m c2c.eval.run --system baseline --stage baseline-v1 --model $(MODEL) \
	  --note "Fair baseline: one direct prompt, full policy, full dossier."

evaluate-tools: setup  ## run the caseworker with tools but no verifier
	$(PY) -m c2c.eval.run --system agent-tools --stage exp1-tools --model $(MODEL) \
	  --note "Caseworker with four tools and a 10-step loop, no verifier."

evaluate: setup  ## run the full agent (tools + independent verifier)
	$(PY) -m c2c.eval.run --system agent --stage final-v1 --model $(MODEL) \
	  --note "Full agent: tools, multi-step loop, independent verifier, one revision."

compare: setup  ## compare the newest baseline with the newest full-agent run
	@b=$$(ls -1t $(RESULTS)/baseline-v1--*.json 2>/dev/null | head -1); \
	 f=$$(ls -1t $(RESULTS)/final-v1--*.json 2>/dev/null | head -1); \
	 if [ -z "$$b" ] || [ -z "$$f" ]; then \
	   echo "need a baseline-v1 and a final-v1 result. Run: make baseline evaluate"; exit 1; fi; \
	 $(PY) -m c2c.eval.report --compare "$$b" "$$f"

reproduce: test baseline evaluate compare  ## the whole reasoning result, end to end
	@echo
	@echo "Reasoning result reproduced. For the durability half: make up failure-tests down"

# --- services ---------------------------------------------------------------

restate-check: setup  ## assert the shared Restate server's other tenants are intact
	$(PY) -m c2c.tools.restate_check

up: setup  ## start the control plane and the C2C Restate service, and register
	@mkdir -p $(RUNDIR)
	@$(PY) -m c2c.tools.restate_check >/dev/null || \
	  (echo "no Restate server at $(RESTATE_ADMIN); see docs/REPRODUCTION.md"; exit 1)
	@$(VENV)/bin/uvicorn c2c.app:app --host 0.0.0.0 --port $(API_PORT) \
	  > $(RUNDIR)/api.log 2>&1 & echo $$! > $(RUNDIR)/api.pid
	@$(PY) -m c2c.restate_service > $(RUNDIR)/svc.log 2>&1 & echo $$! > $(RUNDIR)/svc.pid
	@until curl -sf http://localhost:$(API_PORT)/c2c/health >/dev/null; do sleep 1; done
	@until ss -lnt "sport = :$(SVC_PORT)" | grep -q LISTEN; do sleep 1; done
	@$(MAKE) -s restate-register
	@echo "control plane  http://localhost:$(API_PORT)/docs"
	@echo "sdk endpoint   :$(SVC_PORT)  registered with $(RESTATE_ADMIN)"

restate-register:  ## register C2C's services with the shared Restate server (additive)
	@curl -sf -X POST $(RESTATE_ADMIN)/deployments -H 'content-type: application/json' \
	  -d '{"uri":"http://localhost:$(SVC_PORT)","force":true}' >/dev/null \
	  && echo "registered C2CCase" || echo "registration failed"

restate-deregister:  ## remove ONLY C2C's own deployment
	@$(PY) -m c2c.tools.restate_check >/dev/null 2>&1 || true
	@for id in $$(curl -sf $(RESTATE_ADMIN)/deployments | \
	   $(PY) -c "import json,sys; d=json.load(sys.stdin); \
	   print(' '.join(x['id'] for x in d['deployments'] \
	   if any(s['name'].startswith('C2C') for s in x['services'])))"); do \
	   curl -sf -X DELETE "$(RESTATE_ADMIN)/deployments/$$id?force=true" >/dev/null \
	     && echo "removed C2C deployment $$id"; done
	@$(MAKE) -s restate-check

down:  ## stop only what C2C started, and leave other tenants alone
	@-[ -f $(RUNDIR)/api.pid ] && kill $$(cat $(RUNDIR)/api.pid) 2>/dev/null && rm -f $(RUNDIR)/api.pid
	@-[ -f $(RUNDIR)/svc.pid ] && kill $$(cat $(RUNDIR)/svc.pid) 2>/dev/null && rm -f $(RUNDIR)/svc.pid
	@echo "C2C processes stopped. The shared Restate server was not touched."

# --- durability -------------------------------------------------------------

failure-tests: setup  ## run the six failure-injection scenarios (needs 'make up')
	$(PY) -m c2c.eval.durability

# --- demo -------------------------------------------------------------------

demo: setup  ## walk one case through the full durable lifecycle
	$(PY) -m c2c.tools.demo

demo-reset: setup  ## clear the synthetic airline's state
	@curl -sf -X POST http://localhost:$(API_PORT)/airline/_admin/reset && echo " airline reset"

demo-advance: setup  ## deliver the scripted carrier response to the demo case
	$(PY) -m c2c.tools.demo --advance

demo-approve: setup  ## approve the demo case's pending consequential action
	$(PY) -m c2c.tools.demo --approve

# --- artifacts --------------------------------------------------------------

trajectories: setup  ## re-render every recorded run as judge-readable Markdown
	$(PY) -m c2c.tools.render_trajectories

audit: setup  ## check the repo's claims against its evidence
	$(PY) -m c2c.tools.audit --write
