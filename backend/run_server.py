"""Launcher for Interview Pilot backend.

Bakes in the WebSocket size limit (for up-to-5-minute voice answers) so no
CLI flag is needed:
    python run_server.py
"""
import sys

import uvicorn

from config import settings

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        ws_max_size=settings.ws_max_size,
        reload=False,
    )
