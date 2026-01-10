"""
Quick re-authentication script for Withings
Opens browser automatically and waits for the redirect URL
"""
import webbrowser
from withings_api import WithingsAuth, AuthScope
from config import Config

def reauth():
    config = Config()

    client_id = config.get('WITHINGS_CLIENT_ID')
    client_secret = config.get('WITHINGS_CLIENT_SECRET')
    callback_uri = config.get('WITHINGS_CALLBACK_URI')

    auth = WithingsAuth(
        client_id=client_id,
        consumer_secret=client_secret,
        callback_uri=callback_uri,
        scope=[
            AuthScope.USER_METRICS,
            AuthScope.USER_ACTIVITY
        ]
    )

    # Generate authorization URL
    authorize_url = auth.get_authorize_url()

    print("\n" + "="*80)
    print("WITHINGS RE-AUTHENTICATION")
    print("="*80)
    print("\nOpening browser for authorization...")
    print(f"\nIf browser doesn't open, visit: {authorize_url}")
    print("\nAfter authorizing, paste the FULL redirect URL below.")
    print("="*80 + "\n")

    # Open browser
    webbrowser.open(authorize_url)

    # Get redirect URL from user
    redirect_url = input("Paste the redirect URL here: ").strip()

    # Extract authorization code
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    auth_code = params.get('code', [None])[0]

    if not auth_code:
        print("ERROR: Could not extract authorization code from URL")
        return False

    # Exchange code for credentials
    credentials = auth.get_credentials(auth_code)
    refresh_token = credentials.refresh_token

    # Save to .env file
    config.update_env_file('WITHINGS_REFRESH_TOKEN', refresh_token)

    print("\n" + "="*80)
    print("SUCCESS! Refresh token updated in .env file")
    print("="*80)
    print("\nRestart the app server to use the new token:")
    print("  py -3.12 app.py")
    print("="*80 + "\n")

    return True

if __name__ == '__main__':
    reauth()
