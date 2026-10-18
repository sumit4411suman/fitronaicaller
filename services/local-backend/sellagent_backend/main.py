"""Entry point: `python -m sellagent_backend.main` or the `sellagent-backend` script."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from sellagent_backend.app import create_app
from sellagent_backend.config import APP_VERSION, get_settings


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SELL AGENT local backend")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--export-openapi", default=None, help="write OpenAPI JSON to this path and exit")
    a = ap.parse_args(argv)
    if a.version:
        print(APP_VERSION)
        return 0
    s = get_settings()
    app = create_app(s)
    if a.export_openapi:
        import json
        from pathlib import Path

        Path(a.export_openapi).write_text(json.dumps(app.openapi(), indent=2))
        print(f"wrote {a.export_openapi}")
        return 0
    host, port = a.host or s.host, a.port or s.port
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("Refusing to bind the main API to a non-loopback address. Use the LAN pairing listener instead.", file=sys.stderr)
        return 2
    uvicorn.run(app, host=host, port=port, log_level=s.log_level.lower(), ws_ping_interval=20, ws_ping_timeout=20)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
