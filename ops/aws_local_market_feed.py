"""Local-only OptionX research API entrypoint for AWS Lightsail.

This launches the existing fail-closed API ONLY on 127.0.0.1.
No broker secrets or real-money orders are configured.
"""
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer

# Explicitly expose only this repository root to Python imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from market_api import Handler  # noqa: E402

BIND_ADDRESS = "127.0.0.1"
PORT = 10000

if __name__ == "__main__":
    print(f"OptionX SAFE research API listening on {BIND_ADDRESS}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND_ADDRESS, PORT), Handler).serve_forever()
