"""
Token Storage Module

Provides persistent storage for OAuth tokens (Garmin session, Withings refresh token).
Supports both local file storage and AWS DynamoDB for Lambda deployments.
"""
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TokenStorage(ABC):
    """Abstract base class for token storage backends"""

    @abstractmethod
    def save_garmin_session(self, session_data: Dict[str, Any]) -> None:
        """Save Garmin OAuth session data"""
        pass

    @abstractmethod
    def load_garmin_session(self) -> Optional[Dict[str, Any]]:
        """Load Garmin OAuth session data"""
        pass

    @abstractmethod
    def save_withings_refresh_token(self, refresh_token: str) -> None:
        """Save Withings refresh token"""
        pass

    @abstractmethod
    def load_withings_refresh_token(self) -> Optional[str]:
        """Load Withings refresh token"""
        pass


class LocalTokenStorage(TokenStorage):
    """
    Local file-based token storage.
    Used for local development and the original Flask app.
    """

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(__file__)
        self.base_dir = Path(base_dir)
        self.garmin_session_dir = self.base_dir / '.garmin_session'

    def save_garmin_session(self, session_data: Dict[str, Any]) -> None:
        """Save Garmin session to local directory (garth format)"""
        # garth handles this itself via garth.save()
        # This method exists for interface compatibility
        logger.debug("Local storage: Garmin session managed by garth.save()")

    def load_garmin_session(self) -> Optional[Dict[str, Any]]:
        """Load Garmin session from local directory"""
        # garth handles this itself via garth.resume()
        # Return the path for garth to use
        if self.garmin_session_dir.exists():
            return {'session_dir': str(self.garmin_session_dir)}
        return None

    def save_withings_refresh_token(self, refresh_token: str) -> None:
        """Save Withings refresh token to .env file"""
        env_path = self.base_dir / '.env'

        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()
        else:
            lines = []

        # Update or append the token
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith('WITHINGS_REFRESH_TOKEN='):
                new_lines.append(f'WITHINGS_REFRESH_TOKEN={refresh_token}\n')
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f'WITHINGS_REFRESH_TOKEN={refresh_token}\n')

        with open(env_path, 'w') as f:
            f.writelines(new_lines)

        logger.info("Saved Withings refresh token to .env")

    def load_withings_refresh_token(self) -> Optional[str]:
        """Load Withings refresh token from environment"""
        return os.getenv('WITHINGS_REFRESH_TOKEN')


class DynamoDBTokenStorage(TokenStorage):
    """
    AWS DynamoDB-based token storage.
    Used for Lambda deployments where local filesystem is ephemeral.
    """

    def __init__(self, table_name: str = None):
        import boto3

        self.table_name = table_name or os.environ.get('TOKEN_TABLE_NAME', 'withings-garmin-tokens-prod')
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.table_name)
        self.secrets_client = boto3.client('secretsmanager')
        self.secrets_arn = os.environ.get('SECRETS_ARN')

        logger.info(f"Using DynamoDB table: {self.table_name}")

    def save_garmin_session(self, session_data: Dict[str, Any]) -> None:
        """
        Save Garmin OAuth session to DynamoDB.

        The session_data should contain the garth OAuth tokens.
        """
        try:
            # Serialize the session data
            item = {
                'token_type': 'garmin_session',
                'session_data': json.dumps(session_data),
                'updated_at': int(__import__('time').time())
            }

            self.table.put_item(Item=item)
            logger.info("Saved Garmin session to DynamoDB")

        except Exception as e:
            logger.error(f"Failed to save Garmin session to DynamoDB: {e}")
            raise

    def load_garmin_session(self) -> Optional[Dict[str, Any]]:
        """Load Garmin OAuth session from DynamoDB"""
        try:
            response = self.table.get_item(Key={'token_type': 'garmin_session'})

            if 'Item' in response:
                session_json = response['Item'].get('session_data')
                if session_json:
                    logger.info("Loaded Garmin session from DynamoDB")
                    return json.loads(session_json)

            logger.info("No Garmin session found in DynamoDB")
            return None

        except Exception as e:
            logger.error(f"Failed to load Garmin session from DynamoDB: {e}")
            return None

    def save_withings_refresh_token(self, refresh_token: str) -> None:
        """
        Save Withings refresh token to AWS Secrets Manager.

        We update the existing secret rather than DynamoDB because
        the refresh token is a credential.
        """
        try:
            if not self.secrets_arn:
                logger.warning("SECRETS_ARN not set, cannot save refresh token")
                return

            # Get current secrets
            response = self.secrets_client.get_secret_value(SecretId=self.secrets_arn)
            secrets = json.loads(response['SecretString'])

            # Update the refresh token
            secrets['WITHINGS_REFRESH_TOKEN'] = refresh_token

            # Save back to Secrets Manager
            self.secrets_client.put_secret_value(
                SecretId=self.secrets_arn,
                SecretString=json.dumps(secrets)
            )

            logger.info("Saved Withings refresh token to Secrets Manager")

        except Exception as e:
            logger.error(f"Failed to save Withings refresh token: {e}")
            raise

    def load_withings_refresh_token(self) -> Optional[str]:
        """Load Withings refresh token from Secrets Manager"""
        try:
            if not self.secrets_arn:
                logger.warning("SECRETS_ARN not set")
                return os.getenv('WITHINGS_REFRESH_TOKEN')

            response = self.secrets_client.get_secret_value(SecretId=self.secrets_arn)
            secrets = json.loads(response['SecretString'])
            return secrets.get('WITHINGS_REFRESH_TOKEN')

        except Exception as e:
            logger.error(f"Failed to load Withings refresh token: {e}")
            return None


def get_token_storage() -> TokenStorage:
    """
    Factory function to get the appropriate token storage backend.

    Returns DynamoDBTokenStorage if running in Lambda (AWS_LAMBDA_FUNCTION_NAME set),
    otherwise returns LocalTokenStorage.
    """
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        logger.info("Running in Lambda - using DynamoDB token storage")
        return DynamoDBTokenStorage()
    else:
        logger.info("Running locally - using local file token storage")
        return LocalTokenStorage()
