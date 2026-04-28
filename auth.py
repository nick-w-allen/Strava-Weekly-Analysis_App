import webbrowser
import urllib.parse
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from dotenv import dotenv_values


CLIENT_ID = dotenv_values(".env")["STRAVA_CLIENT_ID"]
REDIRECT_URI = "http://localhost:8080"
SCOPE = "activity:read_all"
TOKEN_FILE = "strava_tokens.json"


def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)


def refresh_tokens(tokens):
    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": tokens["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
    )
    resp.raise_for_status()
    updated = {**tokens, **resp.json()}
    save_tokens(updated)
    return updated


def get_valid_token():
    tokens = load_tokens()
    if tokens.get("expires_at", 0) < time.time() + 60:
        print("Access token expired — refreshing...")
        tokens = refresh_tokens(tokens)
    return tokens["access_token"]


def run_oauth_flow():
    client_secret = input("Paste your Client Secret: ").strip()

    auth_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        "&response_type=code"
        f"&scope={SCOPE}"
    )

    print("\nOpening Strava auth in browser...")
    print(f"If it doesn't open, paste this URL manually:\n{auth_url}\n")
    webbrowser.open(auth_url)

    auth_code = None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            auth_code = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auth complete. Return to terminal.")

        def log_message(self, *args):
            pass

    print("Waiting for Strava authorisation...")
    server = HTTPServer(("localhost", 8080), Handler)
    server.handle_request()

    if not auth_code:
        raise RuntimeError("OAuth callback did not include an auth code")

    resp = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
        },
    )
    resp.raise_for_status()

    tokens = resp.json()
    tokens["client_secret"] = client_secret
    save_tokens(tokens)
    print(f"Auth successful! Token: {tokens['access_token'][:10]}...")
    print(f"Tokens saved to {TOKEN_FILE}")
    return tokens
