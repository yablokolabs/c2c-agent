"""The C2C HTTP process: control plane plus the synthetic airline.

One process, two routers. They are separate concerns but not separate
deployments — splitting them would be two containers and two health checks for
no gain, and the failure-injection suite restarts the whole process anyway.
"""

from fastapi import FastAPI

from c2c.api import router as control_plane
from c2c.simulator import BANNER
from c2c.simulator import router as airline

app = FastAPI(
    title="C2C — Cancellation to Compensation",
    description=f"Control plane and synthetic airline. {BANNER}",
    version="0.1.0",
)
app.include_router(control_plane)
app.include_router(airline)


@app.get("/")
async def root() -> dict:
    return {"service": "c2c", "banner": BANNER,
            "docs": "/docs", "control_plane": "/c2c/health"}
