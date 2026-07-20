#!/usr/bin/env python3
"""
Setup: extract your X session cookies from your real browser and save them
in the format Playwright needs.

You only need two cookies from x.com:
  - auth_token
  - ct0

How to get them:
  1. Open x.com in Chrome/Safari/Firefox (where you're already logged in)
  2. Open DevTools (Cmd+Option+I) → Application tab → Cookies → https://x.com
  3. Find and copy the values for 'auth_token' and 'ct0'

Usage:
    python files/setup_x_session.py

Session is saved to ~/.x_ansible/session.json
"""

import json
import sys
from pathlib import Path

SESSION_DIR = Path.home() / ".x_ansible"
SESSION_FILE = SESSION_DIR / "session.json"


def main():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("X Session Setup")
    print("=" * 60)
    print()
    print("We need two cookies from your real browser where you're")
    print("already logged into X.")
    print()
    print("How to find them:")
    print("  1. Open https://x.com in Chrome (where you're logged in)")
    print("  2. Open DevTools: Cmd+Option+I (Mac) or F12 (Windows/Linux)")
    print("  3. Go to Application tab → Cookies → https://x.com")
    print("  4. Find 'auth_token' and 'ct0' in the list")
    print("  5. Copy each value below")
    print()
    print("(Tip: you can filter the cookie list by typing the name)")
    print()

    auth_token = input("auth_token: ").strip()
    if not auth_token:
        print("ERROR: auth_token is required.")
        sys.exit(1)

    ct0 = input("ct0: ").strip()
    if not ct0:
        print("ERROR: ct0 is required.")
        sys.exit(1)

    # Build Playwright storage_state format
    storage_state = {
        "cookies": [
            {
                "name": "auth_token",
                "value": auth_token,
                "domain": ".x.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
            {
                "name": "ct0",
                "value": ct0,
                "domain": ".x.com",
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            },
        ],
        "origins": [],
    }

    SESSION_FILE.write_text(json.dumps(storage_state, indent=2))
    SESSION_FILE.chmod(0o600)

    print()
    print(f"Session saved to: {SESSION_FILE}")
    print()
    print("Test it with:")
    print("  ansible-playbook post_to_x_browser.yml -e 'post_text=test' --check")
    print()
    print("If your session expires later, just run this script again with")
    print("fresh cookie values.")


if __name__ == "__main__":
    main()
