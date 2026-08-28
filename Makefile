# C2C — Cancellation to Compensation
#
# Everything a judge needs is behind these targets. `make reproduce` runs the
# headline result end to end without Telegram, Docker or a Restate server.

PY      := .venv/bin/python
VENV    := .venv
MODEL   ?= claude-haiku-4-5-20251001
RESULTS := evaluation/results

.DEFAULT_GOAL := help
.PHONY: help setup test baseline evaluate compare reproduce trajectories \
        restate-check restate-register up down failure-tests demo demo-reset \
        demo-advance clean

help:  ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk -F':.*?## ' '{printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	uv venv --python 3.12
	uv pip install -e ".[dev]"

setup: $(VENV)/bin/python  ## create the venv and install C2C
	@$(PY) -c "import c2c; print('c2c', c2c.__version__, 'ready')"
	@$(PY) -c "from c2c.llm import choose_backend; \
	  print('model backend:', choose_backend())"

test: setup  ## run the test suite
	$(PY) -m pytest tests/ -q

baseline: setup  ## run the baseline over the 20-case benchmark
	$(PY) -m c2c.eval.run --system baseline --stage baseline-v0 --model $(MODEL) \
	  --note "Fair baseline: one direct prompt, full policy, full dossier."

evaluate: setup  ## run the full agent over the 20-case benchmark
	$(PY) -m c2c.eval.run --system agent --stage final-v1 --model $(MODEL) \
	  --note "Full agent: tools, structured extraction, independent verifier."

compare: setup  ## compare the newest baseline run with the newest agent run
	@b=$$(ls -1t $(RESULTS)/baseline-v0--*.json 2>/dev/null | head -1); \
	 f=$$(ls -1t $(RESULTS)/final-v1--*.json 2>/dev/null | head -1); \
	 if [ -z "$$b" ] || [ -z "$$f" ]; then \
	   echo "need one baseline-v0 and one final-v1 result; run 'make baseline evaluate'"; exit 1; fi; \
	 $(PY) -m c2c.eval.report --compare "$$b" "$$f"

trajectories: setup  ## re-render every recorded run as Markdown
	$(PY) -m c2c.tools.render_trajectories

clean:  ## remove the venv and caches, never results or trajectories
	rm -rf $(VENV) .pytest_cache **/__pycache__
