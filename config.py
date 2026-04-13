"""
Configuration management. Local-daemon flavor: loads from .env file only,
no AWS Secrets Manager / Lambda branches.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for the local daemon."""

    def __init__(self, env_file: str = ".env"):
        from dotenv import load_dotenv

        env_path = Path(__file__).parent / env_file
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("Loaded configuration from %s", env_path)
        else:
            logger.warning("No %s file found, using process environment only", env_path)

        self.config = {
            "WITHINGS_CLIENT_ID": os.getenv("WITHINGS_CLIENT_ID"),
            "WITHINGS_CLIENT_SECRET": os.getenv("WITHINGS_CLIENT_SECRET"),
            "WITHINGS_REFRESH_TOKEN": os.getenv("WITHINGS_REFRESH_TOKEN"),
            "WITHINGS_CALLBACK_URI": os.getenv("WITHINGS_CALLBACK_URI", "http://localhost:5000/callback"),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
        }

        self._validate()

    def _validate(self) -> None:
        required = ["WITHINGS_CLIENT_ID", "WITHINGS_CLIENT_SECRET", "WITHINGS_REFRESH_TOKEN"]
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            logger.warning("Missing required configuration: %s", ", ".join(missing))
        else:
            logger.info("All required Withings configuration present")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value) -> None:
        self.config[key] = value

    def update_env_file(self, key: str, value: str, env_file: str = ".env") -> None:
        """Persist a configuration value to the .env file and in-memory config."""
        env_path = Path(__file__).parent / env_file

        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        self.config[key] = value
        logger.info("Updated %s in %s", key, env_path.name)
