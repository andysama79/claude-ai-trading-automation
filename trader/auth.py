"""Manual-mode Kite Connect session generator.

Run this once each trading day (before starting `python -m trader`) when
`auth.mode: manual` in config.yaml. Kite Connect access tokens expire daily;
this script drives the interactive login flow and caches the resulting
access_token to `.kite_session`, which `KiteBroker._load_session()` reads
at startup.

Usage:
    python -m trader.auth

Requires KITE_API_KEY and KITE_API_SECRET in the environment (.env).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from kiteconnect import KiteConnect

_SESSION_FILE = Path(".kite_session")


def _get_credentials() -> tuple[str, str]:
    load_dotenv()
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key or not api_secret:
        print(
            "KITE_API_KEY and/or KITE_API_SECRET missing from environment.\n"
            "Set them in .env (see .env.example) before running this script.",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key, api_secret


def run() -> None:
    api_key, api_secret = _get_credentials()
    kite = KiteConnect(api_key=api_key)

    print("1. Open this URL in a browser and log in:")
    print(f"   {kite.login_url()}")
    print()
    print("2. After login, Kite redirects to your registered redirect URL")
    print("   with a `request_token` query parameter. Copy that value.")
    print()

    request_token = input("Paste request_token here: ").strip()
    if not request_token:
        print("No request_token provided, aborting.", file=sys.stderr)
        sys.exit(1)

    try:
        session = kite.generate_session(request_token, api_secret=api_secret)
    except Exception as exc:  # kiteconnect raises its own exception types
        print(f"Failed to exchange request_token for a session: {exc}", file=sys.stderr)
        sys.exit(1)

    access_token = session["access_token"]
    _SESSION_FILE.write_text(access_token)
    _SESSION_FILE.chmod(0o600)
    print(f"Session cached to {_SESSION_FILE.resolve()} (access_token, mode 0600).")
    print("You can now start the trader: python -m trader --config config.yaml")


if __name__ == "__main__":
    run()
