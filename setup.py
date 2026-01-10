"""
Setup script for initial OAuth authentication with Withings
Run this once to get your refresh token
"""
import os
import sys
import logging
from withings_api import WithingsAuth, AuthScope
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_withings_oauth():
    """
    Interactive setup for Withings OAuth

    This will:
    1. Generate an authorization URL
    2. Wait for you to visit it and authorize
    3. Extract the refresh token
    4. Save it to your .env file
    """
    config = Config()

    client_id = config.get('WITHINGS_CLIENT_ID')
    client_secret = config.get('WITHINGS_CLIENT_SECRET')
    callback_uri = config.get('WITHINGS_CALLBACK_URI')

    if not client_id or not client_secret:
        logger.error("Missing WITHINGS_CLIENT_ID or WITHINGS_CLIENT_SECRET in .env file")
        logger.error("Please create a Withings app at: https://developer.withings.com/dashboard")
        return False

    try:
        auth = WithingsAuth(
            client_id=client_id,
            consumer_secret=client_secret,
            callback_uri=callback_uri,
            scope=[
                AuthScope.USER_METRICS,  # Access to weight and other measurements
                AuthScope.USER_ACTIVITY   # Optional: activity data
            ]
        )

        # Generate authorization URL
        authorize_url = auth.get_authorize_url()

        print("\n" + "=" * 80)
        print("WITHINGS OAUTH SETUP")
        print("=" * 80)
        print("\nStep 1: Visit this URL in your browser to authorize:")
        print(f"\n{authorize_url}\n")
        print("Step 2: After authorizing, you'll be redirected to a URL like:")
        print(f"{callback_uri}?code=XXXXX&state=XXXXX")
        print("\nStep 3: Copy the FULL redirect URL and paste it below")
        print("=" * 80 + "\n")

        redirect_url = input("Paste the full redirect URL here: ").strip()

        # Extract the authorization code
        if 'code=' in redirect_url:
            # Parse the URL to get the code
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(redirect_url)
            params = parse_qs(parsed.query)
            auth_code = params.get('code', [None])[0]

            if auth_code:
                logger.info("Authorization code received, exchanging for tokens...")

                # Exchange code for credentials
                credentials = auth.get_credentials(auth_code)

                # Extract refresh token
                refresh_token = credentials.refresh_token

                logger.info("Successfully obtained refresh token!")

                # Save to .env file
                config.update_env_file('WITHINGS_REFRESH_TOKEN', refresh_token)

                print("\n" + "=" * 80)
                print("SUCCESS! Refresh token saved to .env file")
                print("=" * 80)
                print("\nYou can now run the webhook server with:")
                print("  python app.py")
                print("\nAnd subscribe to webhooks with:")
                print("  python webhook_manager.py subscribe <your-ngrok-url>")
                print("=" * 80 + "\n")

                return True
            else:
                logger.error("Could not extract authorization code from URL")
                return False
        else:
            logger.error("Invalid redirect URL (missing 'code' parameter)")
            return False

    except Exception as e:
        logger.error(f"Setup failed: {str(e)}", exc_info=True)
        return False


if __name__ == '__main__':
    print("\nWithings to Garmin Webhook Sync - Initial Setup\n")

    success = setup_withings_oauth()

    if success:
        sys.exit(0)
    else:
        print("\nSetup failed. Please check the errors above and try again.")
        sys.exit(1)
