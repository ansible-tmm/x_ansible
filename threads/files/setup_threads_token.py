#!/usr/bin/env python3
"""Setup script to obtain a long-lived Threads access token.

This script handles the OAuth 2.0 flow for the Threads API:
1. Opens the authorization URL in your browser
2. Starts a local HTTPS server to catch the redirect
3. Exchanges the auth code for a short-lived token
4. Exchanges that for a long-lived token (60 days)
5. Fetches your Threads user ID
6. Saves everything to threads/vars/token.json

Prerequisites:
    export THREADS_APP_ID="your_threads_app_id"
    export THREADS_APP_SECRET="your_threads_app_secret"

    Your redirect URI in Meta Developer Portal must be:
        https://localhost:8080/callback
"""

import http.server
import json
import os
import ssl
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests

REDIRECT_PORT = 8080
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"https://localhost:{REDIRECT_PORT}{REDIRECT_PATH}"

THREADS_AUTH_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_LONG_LIVED_URL = "https://graph.threads.net/access_token"
THREADS_ME_URL = "https://graph.threads.net/v1.0/me"

TOKEN_FILE = Path(__file__).resolve().parent.parent / "vars" / "token.json"

auth_code = None
server_ready = threading.Event()


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == REDIRECT_PATH and "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family: sans-serif; text-align: center; padding: 4rem;">
                <h2>Authorization successful!</h2>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
            """)
        elif "error" in params:
            error = params.get("error_description", params.get("error", ["Unknown"]))[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def generate_self_signed_cert():
    """Generate a temporary self-signed cert for the local HTTPS server."""
    cert_dir = Path(__file__).resolve().parent / ".certs"
    cert_dir.mkdir(exist_ok=True)
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    if not cert_file.exists():
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_file), "-out", str(cert_file),
            "-days", "1", "-nodes",
            "-subj", "/CN=localhost"
        ], capture_output=True, check=True)

    return str(cert_file), str(key_file)


def start_local_server():
    """Start an HTTPS server to catch the OAuth redirect."""
    cert_file, key_file = generate_self_signed_cert()

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), OAuthHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    server_ready.set()
    server.handle_request()
    return server


def get_short_lived_token(app_id, app_secret, code):
    """Exchange authorization code for a short-lived token."""
    resp = requests.post(THREADS_TOKEN_URL, data={
        "client_id": app_id,
        "client_secret": app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code": code,
    })
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Token exchange failed: {data}")
    return data["access_token"]


def get_long_lived_token(app_secret, short_token):
    """Exchange short-lived token for a long-lived token (60 days)."""
    resp = requests.get(THREADS_LONG_LIVED_URL, params={
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    })
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Long-lived token exchange failed: {data}")
    return data["access_token"], data.get("expires_in", 5184000)


def get_user_id(access_token):
    """Fetch the Threads user ID."""
    resp = requests.get(THREADS_ME_URL, params={
        "fields": "id,username,threads_profile_picture_url",
        "access_token": access_token,
    })
    resp.raise_for_status()
    data = resp.json()
    return data["id"], data.get("username", "unknown")


def main():
    app_id = os.environ.get("THREADS_APP_ID")
    app_secret = os.environ.get("THREADS_APP_SECRET")

    if not app_id or not app_secret:
        print("Error: Set THREADS_APP_ID and THREADS_APP_SECRET environment variables.")
        print("  export THREADS_APP_ID='your_threads_app_id'")
        print("  export THREADS_APP_SECRET='your_threads_app_secret'")
        sys.exit(1)

    print("=" * 60)
    print("  Threads API Token Setup")
    print("=" * 60)
    print()
    print(f"App ID: {app_id}")
    print(f"Redirect URI: {REDIRECT_URI}")
    print()

    # Start local HTTPS server in background
    server_thread = threading.Thread(target=start_local_server, daemon=True)
    server_thread.start()
    server_ready.wait()

    # Build authorization URL
    auth_params = urllib.parse.urlencode({
        "client_id": app_id,
        "redirect_uri": REDIRECT_URI,
        "scope": "threads_basic,threads_content_publish",
        "response_type": "code",
    })
    auth_url = f"{THREADS_AUTH_URL}?{auth_params}"

    print("Opening browser for authorization...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization callback...")
    print("(Your browser may warn about the self-signed certificate — click 'Advanced' > 'Proceed')\n")

    server_thread.join(timeout=120)

    if not auth_code:
        print("Error: Did not receive authorization code within 2 minutes.")
        sys.exit(1)

    print(f"Got authorization code: {auth_code[:10]}...")
    print()

    # Exchange for short-lived token
    print("Exchanging for short-lived token...")
    short_token = get_short_lived_token(app_id, app_secret, auth_code)
    print(f"  Short-lived token: {short_token[:15]}...")

    # Exchange for long-lived token
    print("Exchanging for long-lived token (60 days)...")
    long_token, expires_in = get_long_lived_token(app_secret, short_token)
    days = expires_in // 86400
    print(f"  Long-lived token: {long_token[:15]}...")
    print(f"  Expires in: {days} days")

    # Get user ID
    print("Fetching Threads user ID...")
    user_id, username = get_user_id(long_token)
    print(f"  User ID: {user_id}")
    print(f"  Username: @{username}")

    # Save token
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "access_token": long_token,
        "user_id": user_id,
        "username": username,
        "expires_in_days": days,
    }
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    print(f"\nToken saved to: {TOKEN_FILE}")

    print()
    print("=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print()
    print("You can now post to Threads:")
    print("  ansible-playbook threads/post_to_threads.yml -e 'post_text=hello from ansible'")
    print()
    print("Or set these env vars if you prefer not to use the saved file:")
    print(f"  export THREADS_ACCESS_TOKEN='{long_token}'")
    print(f"  export THREADS_USER_ID='{user_id}'")
    print()
    print(f"Token expires in {days} days. Re-run this script to refresh.")


if __name__ == "__main__":
    main()
