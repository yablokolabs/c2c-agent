# C2C — control plane, durable workflow service, and Telegram adapter.
#
# One image, three entrypoints. They are separate processes, not separate
# builds: they share all their code, and building three images to run the same
# package would be ceremony.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml README.md ./
COPY c2c ./c2c
RUN pip install --no-cache-dir -e .

COPY benchmark ./benchmark
COPY agents ./agents
COPY prompts ./prompts

# Live cases and trajectories are written at runtime and mounted from the host.
RUN mkdir -p data/cases trajectories/runs evaluation/results

ENV PYTHONUNBUFFERED=1 \
    C2C_RESTATE_INGRESS=http://restate:8080 \
    C2C_CONTROL_PLANE=http://api:8099 \
    C2C_AIRLINE=http://api:8099/airline \
    C2C_API=http://api:8099

EXPOSE 8099 9095

CMD ["uvicorn", "c2c.app:app", "--host", "0.0.0.0", "--port", "8099"]
