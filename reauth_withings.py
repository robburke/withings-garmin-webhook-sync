"""
Quick re-authentication script for Withings, using raw HTTP (no withings-api dep).

Run this when the refresh token in .env stops working (e.g., revoked from the
Withings dashboard, or after long inactivity). It walks you through the OAuth2
authorization-code flow and writes a fresh refresh token back to .env.
"""

import sys
import webbrowser
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from config import Config

AUTHORIZE_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
SCOPE = "user.metrics,user.activity"


def reauth() -> bool:
    config = Config()

    client_id = config.get("WITHINGS_CLIENT_ID")
    client_secret = config.get("WITHINGS_CLIENT_SECRET")
    callback_uri = config.get("WITHINGS_CALLBACK_URI")

    if not client_id or not client_secret or not callback_uri:
        print("ERROR: Missing WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, or WITHINGS_CALLBACK_URI in .env")
        return False

    authorize_params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": SCOPE,
        "redirect_uri": callback_uri,
        "state": "reauth",
    }
    authorize_url = f"{AUTHORIZE_URL}?{urlencode(authorize_params)}"

    print("\n" + "=" * 80)
    print("WITHINGS RE-AUTHENTICATION")
    print("=" * 80)
    print("\nOpening browser for authorization...")
    print(f"\nIf the browser doesn't open, visit:\n{authorize_url}")
    print("\nAfter authorizing, paste the FULL redirect URL below.")
    print("=" * 80 + "\n")

    webbrowser.open(authorize_url)
    redirect_url = input("Paste the redirect URL here: ").strip()

    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    auth_code = params.get("code", [None])[0]

    if not auth_code:
        print("ERROR: Could not extract authorization code from URL")
        return False

    token_params = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "redirect_uri": callback_uri,
    }

    response = requests.post(TOKEN_URL, params=token_params, timeout=30)
    resp_json = response.json()

    if resp_json.get("status") != 0:
        print(f"ERROR: Withings token exchange failed: {resp_json}")
        return False

    body = resp_json.get("body", {})
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        print(f"ERROR: No refresh_token in response body: {body}")
        return False

    config.update_env_file("WITHINGS_REFRESH_TOKEN", refresh_token)

    print("\n" + "=" * 80)
    print("SUCCESS! Refresh token updated in .env file")
    print("=" * 80 + "\n")
    return True


if __name__ == "__main__":
    sys.exit(0 if reauth() else 1)
