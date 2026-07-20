#!/usr/bin/env python3
"""
One-time OAuth 2.0 setup for LinkedIn API access.

This script:
1. Opens your browser to LinkedIn's authorization page
2. Starts a local HTTP server to catch the redirect
3. Exchanges the auth code for an access token
4. Fetches your member ID (person URN)
5. Saves everything to ~/.x_ansible/linkedin.json

Usage:
    export LINKEDIN_CLIENT_ID="your-client-id"
    export LINKEDIN_CLIENT_SECRET="your-client-secret"
    python linkedin/files/setup_linkedin_token.py

Re-run this every ~60 days when the token expires.
"""

import http.server
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

CONFIG_DIR = Path.home() / ".x_ansible"
CONFIG_FILE = CONFIG_DIR / "linkedin.json"
REDIRECT_PORT = 8000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = "openid profile email w_member_social"

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth redirect and extracts the authorization code."""

    auth_code = None
    error = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Success!</h2>"
                b"<p>Authorization code received. You can close this tab.</p>"
                b"</body></html>"
            )
        elif "error" in params:
            OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h2>Error</h2><p>{OAuthCallbackHandler.error}</p></body></html>".encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


def main():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")

    if not client_id:
        print("ERROR: Set LINKEDIN_CLIENT_ID environment variable.")
        print("  export LINKEDIN_CLIENT_ID=\"your-client-id\"")
        sys.exit(1)

    if not client_secret:
        print("ERROR: Set LINKEDIN_CLIENT_SECRET environment variable.")
        print("  export LINKEDIN_CLIENT_SECRET=\"your-client-secret\"")
        sys.exit(1)

    print("=" * 60)
    print("LinkedIn OAuth Setup")
    print("=" * 60)
    print()
    print(f"Client ID: {client_id}")
    print(f"Redirect:  {REDIRECT_URI}")
    print()
    print("A browser window will open for you to authorize the app.")
    print("After approving, you'll be redirected back here automatically.")
    print()

    # Start local server to catch the redirect
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    # Build authorization URL and open browser
    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": "ansible_linkedin_setup",
    })
    authorize_url = f"{AUTH_URL}?{auth_params}"

    print(f"Opening browser...")
    print(f"  {authorize_url}")
    print()
    webbrowser.open(authorize_url)

    # Wait for the callback
    print("Waiting for authorization...")
    server_thread.join(timeout=120)
    server.server_close()

    if OAuthCallbackHandler.error:
        print(f"\nERROR: {OAuthCallbackHandler.error}")
        sys.exit(1)

    if not OAuthCallbackHandler.auth_code:
        print("\nERROR: No authorization code received (timed out after 120s).")
        sys.exit(1)

    print("Authorization code received. Exchanging for access token...")

    # Exchange code for token
    token_resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": OAuthCallbackHandler.auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    if token_resp.status_code != 200:
        print(f"\nERROR: Token exchange failed (HTTP {token_resp.status_code}):")
        print(f"  {token_resp.text}")
        sys.exit(1)

    token_data = token_resp.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 5184000)

    print(f"Access token obtained (expires in {expires_in // 86400} days).")

    # Fetch member ID (person URN)
    print("Fetching your member ID...")
    userinfo_resp = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if userinfo_resp.status_code != 200:
        print(f"\nERROR: Failed to fetch user info (HTTP {userinfo_resp.status_code}):")
        print(f"  {userinfo_resp.text}")
        sys.exit(1)

    userinfo = userinfo_resp.json()
    member_id = userinfo.get("sub", "")
    name = userinfo.get("name", "Unknown")

    if not member_id:
        print("\nERROR: Could not determine member ID from userinfo response.")
        sys.exit(1)

    person_urn = f"urn:li:person:{member_id}"

    # Save config
    config = {
        "access_token": access_token,
        "person_urn": person_urn,
        "member_id": member_id,
        "name": name,
        "expires_in_seconds": expires_in,
    }

    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    CONFIG_FILE.chmod(0o600)

    print()
    print(f"Authenticated as: {name}")
    print(f"Person URN:        {person_urn}")
    print(f"Saved to:          {CONFIG_FILE}")
    print()
    print("You're all set! Environment variables for the playbook:")
    print()
    print(f'  export LINKEDIN_ACCESS_TOKEN="{access_token}"')
    print(f'  export LINKEDIN_PERSON_URN="{person_urn}"')
    print()
    print("Or just run the playbook — the module reads from")
    print(f"  {CONFIG_FILE} automatically.")
    print()
    print(f"Token expires in ~{expires_in // 86400} days. Re-run this script to refresh.")


if __name__ == "__main__":
    main()
