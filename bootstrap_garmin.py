"""
Bootstrap Garmin session for Lambda deployment.
This script authenticates with Garmin locally (handles MFA if needed)
and uploads the session to DynamoDB for the Lambda function to use.
"""
import os
import sys
import json
import boto3
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Garth and garminconnect for authentication
import garth
from garminconnect import Garmin

# Session directory
SESSION_DIR = os.path.join(os.path.dirname(__file__), '.garmin_session')


def authenticate_garmin():
    """Authenticate with Garmin Connect"""
    email = os.getenv('GARMIN_EMAIL')
    password = os.getenv('GARMIN_PASSWORD')

    if not email or not password:
        print("Error: GARMIN_EMAIL and GARMIN_PASSWORD must be set in .env")
        sys.exit(1)

    print(f"\nAuthenticating with Garmin as: {email}")

    # Create session directory
    os.makedirs(SESSION_DIR, exist_ok=True)

    # Try to resume existing session first
    try:
        garth.resume(SESSION_DIR)
        client = Garmin()
        client.garth = garth.client
        name = client.get_full_name()
        print(f"Existing session is valid. Logged in as: {name}")
        return True
    except Exception as e:
        print(f"No valid existing session: {e}")

    # Login fresh (may trigger MFA prompt in browser)
    print("\nLogging in... (check your browser if MFA is required)")
    try:
        garth.login(email, password)
        garth.client.domain = "garmin.com"
        garth.save(SESSION_DIR)

        # Verify login
        client = Garmin()
        client.garth = garth.client
        name = client.get_full_name()
        print(f"\nSuccessfully authenticated as: {name}")
        return True

    except Exception as e:
        print(f"\nAuthentication failed: {e}")
        return False


def upload_session_to_dynamodb():
    """Upload the local Garmin session to DynamoDB"""

    # Read session files
    session_data = {}

    oauth1_path = os.path.join(SESSION_DIR, 'oauth1_token.json')
    if os.path.exists(oauth1_path):
        with open(oauth1_path, 'r') as f:
            session_data['oauth1_token'] = json.load(f)
        print(f"Loaded OAuth1 token")

    oauth2_path = os.path.join(SESSION_DIR, 'oauth2_token.json')
    if os.path.exists(oauth2_path):
        with open(oauth2_path, 'r') as f:
            session_data['oauth2_token'] = json.load(f)
        print(f"Loaded OAuth2 token")

    if not session_data:
        print("Error: No session files found")
        return False

    # Upload to DynamoDB - use TOKEN_TABLE_NAME env var or default to prod table name
    # Table name matches template.yaml: withings-garmin-tokens-${Environment}
    table_name = os.environ.get('TOKEN_TABLE_NAME', 'withings-garmin-tokens-prod')

    print(f"\nUploading session to DynamoDB table: {table_name}")

    try:
        dynamodb = boto3.resource('dynamodb', region_name='ca-central-1')
        table = dynamodb.Table(table_name)

        table.put_item(Item={
            'token_type': 'garmin_session',
            'session_data': json.dumps(session_data),
            'updated_at': int(datetime.now().timestamp())
        })

        print("Successfully uploaded Garmin session to DynamoDB!")
        return True

    except Exception as e:
        print(f"Failed to upload to DynamoDB: {e}")
        return False


def main():
    print("=" * 60)
    print("Garmin Session Bootstrap for Lambda")
    print("=" * 60)

    # Step 1: Authenticate locally
    if not authenticate_garmin():
        print("\nFailed to authenticate. Please try again.")
        sys.exit(1)

    # Step 2: Upload to DynamoDB
    print("\n" + "-" * 60)
    if not upload_session_to_dynamodb():
        print("\nFailed to upload session to DynamoDB.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Bootstrap complete! Lambda can now use the Garmin session.")
    print("=" * 60)


if __name__ == '__main__':
    main()
