"""Container healthcheck entrypoint."""

from __future__ import annotations

import json
import os
import sys
from http.client import HTTPConnection


def main() -> int:
    port = int(os.environ.get("NCL_PORT", "8000"))
    try:
        connection = HTTPConnection("127.0.0.1", port, timeout=3)
        connection.request("GET", "/v1/health")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return 0 if response.status == 200 and payload.get("status") in {"ok", "degraded"} else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
