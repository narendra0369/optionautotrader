"""Local-only OptionX research API entrypoint for AWS Lightsail.

Do not expose broker-login endpoints publicly or enable real-money trading.
The upstream market_api Handler returns hard-locked order routes.
"""
from http.server import ThreadingHTTPServer
from market_api import Handler

BIND_ADDRESS = "127.0.0.1"
PORT = 10000

if __name__ == "__main__":
    print(f"OptionX SAFE research API listening on {BIND_ADDRESS}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND_ADDRESS, PORT), Handler).serve_forever()
