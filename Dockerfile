# C2C — control plane, durable workflow service, and Telegram adapter.
#
# One image, three entrypoints. They are separate processes, not separate
# builds: they share all their code, and building three images to run the same
# package would be ceremony.

FROM python:3.12-slim

# curl for health checks; node and the Claude CLI so the container can reuse a
# host login instead of requiring an API key. Without the CLI installed, the
# ~/.claude mount documented in docker-compose.yml would silently do nothing.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml README.md ./
COPY c2c ./c2c
# Including the dev extras, so the test suite runs inside the container. The
# reproduction guide tells a judge to run it there, and without pytest that
# instruction was wrong.
RUN pip install --no-cache-dir -e ".[dev]"

COPY benchmark ./benchmark
COPY agents ./agents
COPY prompts ./prompts
COPY tests ./tests

# Live cases and trajectories are written at runtime and mounted from the host.
RUN mkdir -p data/cases trajectories/runs evaluation/results

ENV PYTHONUNBUFFERED=1 \
    C2C_RESTATE_INGRESS=http://restate:8080 \
    C2C_CONTROL_PLANE=http://api:8099 \
    C2C_AIRLINE=http://api:8099/airline \
    C2C_API=http://api:8099

EXPOSE 8099 9095

CMD ["uvicorn", "c2c.app:app", "--host", "0.0.0.0", "--port", "8099"]
