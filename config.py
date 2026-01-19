"""
Configuration management
Loads settings from environment variables, .env file, or AWS Secrets Manager (Lambda)
"""
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_lambda_environment() -> bool:
    """Check if running in AWS Lambda"""
    return bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))


class Config:
    """Configuration manager - supports both local and Lambda environments"""

    def __init__(self, env_file: str = '.env'):
        """
        Initialize configuration

        Args:
            env_file: Path to .env file (default: .env) - used only for local development
        """
        self._token_storage = None

        if is_lambda_environment():
            self._load_lambda_config()
        else:
            self._load_local_config(env_file)

        self._validate()

    def _load_local_config(self, env_file: str):
        """Load configuration from .env file (local development)"""
        from dotenv import load_dotenv

        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"Loaded configuration from {env_file}")
        else:
            logger.warning(f"No {env_file} file found, using environment variables only")

        self.config = {
            # Withings credentials
            'WITHINGS_CLIENT_ID': os.getenv('WITHINGS_CLIENT_ID'),
            'WITHINGS_CLIENT_SECRET': os.getenv('WITHINGS_CLIENT_SECRET'),
            'WITHINGS_REFRESH_TOKEN': os.getenv('WITHINGS_REFRESH_TOKEN'),
            'WITHINGS_CALLBACK_URI': os.getenv('WITHINGS_CALLBACK_URI', 'http://localhost:5000/callback'),

            # Garmin credentials
            'GARMIN_EMAIL': os.getenv('GARMIN_EMAIL'),
            'GARMIN_PASSWORD': os.getenv('GARMIN_PASSWORD'),

            # App settings
            'PORT': int(os.getenv('PORT', 5000)),
            'LOG_LEVEL': os.getenv('LOG_LEVEL', 'INFO'),

            # Environment indicator
            'IS_LAMBDA': False,
        }

    def _load_lambda_config(self):
        """Load configuration from AWS Secrets Manager (Lambda environment)"""
        import boto3

        logger.info("Loading configuration from AWS Secrets Manager")

        secrets_arn = os.environ.get('SECRETS_ARN')
        if not secrets_arn:
            raise ValueError("SECRETS_ARN environment variable not set")

        # Fetch secrets from Secrets Manager
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=secrets_arn)
        secrets = json.loads(response['SecretString'])

        self.config = {
            # Withings credentials (from Secrets Manager)
            'WITHINGS_CLIENT_ID': secrets.get('WITHINGS_CLIENT_ID'),
            'WITHINGS_CLIENT_SECRET': secrets.get('WITHINGS_CLIENT_SECRET'),
            'WITHINGS_REFRESH_TOKEN': secrets.get('WITHINGS_REFRESH_TOKEN'),
            'WITHINGS_CALLBACK_URI': os.environ.get('WITHINGS_CALLBACK_URI', ''),

            # Garmin credentials (from Secrets Manager)
            'GARMIN_EMAIL': secrets.get('GARMIN_EMAIL'),
            'GARMIN_PASSWORD': secrets.get('GARMIN_PASSWORD'),

            # App settings
            'PORT': 443,  # Not used in Lambda
            'LOG_LEVEL': os.environ.get('LOG_LEVEL', 'INFO'),

            # Environment indicator
            'IS_LAMBDA': True,

            # AWS-specific settings
            'TOKEN_TABLE_NAME': os.environ.get('TOKEN_TABLE_NAME'),
            'SECRETS_ARN': secrets_arn,
        }

        logger.info("Configuration loaded from Secrets Manager")

    def _validate(self):
        """Validate that required configuration is present"""
        required = [
            'WITHINGS_CLIENT_ID',
            'WITHINGS_CLIENT_SECRET',
            'GARMIN_EMAIL',
            'GARMIN_PASSWORD'
        ]

        missing = [key for key in required if not self.config.get(key)]

        if missing:
            logger.warning(f"Missing required configuration: {', '.join(missing)}")
            logger.warning("Please set these in your .env file or environment variables")
        else:
            logger.info("All required configuration present")

    def get(self, key: str, default=None):
        """
        Get a configuration value

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value
        """
        return self.config.get(key, default)

    def set(self, key: str, value):
        """
        Set a configuration value (runtime only, not persisted)

        Args:
            key: Configuration key
            value: Value to set
        """
        self.config[key] = value

    def update_env_file(self, key: str, value: str, env_file: str = '.env'):
        """
        Update a configuration value persistently.

        In local mode: updates the .env file
        In Lambda mode: updates AWS Secrets Manager

        Args:
            key: Configuration key
            value: Value to set
            env_file: Path to .env file (local mode only)
        """
        if self.config.get('IS_LAMBDA'):
            self._update_secrets_manager(key, value)
        else:
            self._update_local_env_file(key, value, env_file)

        # Update in-memory config
        self.config[key] = value

    def _update_local_env_file(self, key: str, value: str, env_file: str):
        """Update a value in the local .env file"""
        env_path = Path(env_file)

        # Read existing content
        if env_path.exists():
            with open(env_path, 'r') as f:
                lines = f.readlines()
        else:
            lines = []

        # Update or append the key
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f'{key}='):
                new_lines.append(f'{key}={value}\n')
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f'{key}={value}\n')

        # Write back
        with open(env_path, 'w') as f:
            f.writelines(new_lines)

        logger.info(f"Updated {key} in {env_file}")

    def _update_secrets_manager(self, key: str, value: str):
        """Update a value in AWS Secrets Manager"""
        import boto3

        secrets_arn = self.config.get('SECRETS_ARN')
        if not secrets_arn:
            logger.warning("SECRETS_ARN not set, cannot update secrets")
            return

        try:
            client = boto3.client('secretsmanager')

            # Get current secrets
            response = client.get_secret_value(SecretId=secrets_arn)
            secrets = json.loads(response['SecretString'])

            # Update the specific key
            secrets[key] = value

            # Save back to Secrets Manager
            client.put_secret_value(
                SecretId=secrets_arn,
                SecretString=json.dumps(secrets)
            )

            logger.info(f"Updated {key} in Secrets Manager")

        except Exception as e:
            logger.error(f"Failed to update {key} in Secrets Manager: {e}")
            raise
