"""Serve the C2C Restate services.

Restate speaks HTTP/2 bidirectional streaming to an SDK endpoint, so this needs
hypercorn rather than uvicorn. Runs on its own port; the control plane is a
separate process, so restarting one does not take the other down — which the
failure-injection suite depends on.
"""

import asyncio
import os

from hypercorn.asyncio import serve
from hypercorn.config import Config

from c2c.workflow import app

PORT = int(os.environ.get("C2C_RESTATE_SERVICE_PORT", "9095"))


def main() -> None:
    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    config.h2_max_concurrent_streams = 2048
    config.keep_alive_timeout = 900
    print(f"C2C Restate services listening on :{PORT}")
    asyncio.run(serve(app, config))


if __name__ == "__main__":
    main()
