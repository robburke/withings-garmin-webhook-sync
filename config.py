"""
Configuration management
Loads settings from environment variables and .env file
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager"""

    def __init__(self, env_file: str = '.env'):
        """
        Initialize configuration

        Args:
            env_file: Path to .env file (default: .env)
        """
        # Load .env file if it exists
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
        }

        self._validate()

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
        Update a value in the .env file

        Args:
            key: Configuration key
            value: Value to set
            env_file: Path to .env file
        """
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

        # Update in-memory config
        self.config[key] = value
