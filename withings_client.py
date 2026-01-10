"""
Withings API Client
Handles authentication and data retrieval from Withings using raw requests
Based on withings-sync implementation to avoid pydantic conflicts
"""
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict

logger = logging.getLogger(__name__)

TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
GETMEAS_URL = "https://wbsapi.withings.net/measure?action=getmeas"
NOTIFY_URL = "https://wbsapi.withings.net/notify"


class WithingsClient:
    """Wrapper for Withings API using raw requests (no pydantic dependency)"""

    def __init__(self, config):
        self.config = config
        self.access_token = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Withings API"""
        try:
            client_id = self.config.get('WITHINGS_CLIENT_ID')
            client_secret = self.config.get('WITHINGS_CLIENT_SECRET')
            refresh_token = self.config.get('WITHINGS_REFRESH_TOKEN')

            if not refresh_token:
                logger.warning("No refresh token found. Run initial setup first.")
                raise ValueError("No refresh token configured. Run initial setup first.")

            logger.info("Authenticating with Withings using refresh token")

            # Refresh the access token
            params = {
                "action": "requesttoken",
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            }

            response = requests.post(TOKEN_URL, params=params, timeout=30)
            resp_json = response.json()

            status = resp_json.get("status")
            if status != 0:
                logger.error(f"Withings API returned error status: {status}")
                logger.error(f"Response: {resp_json}")
                raise Exception(f"Withings auth failed with status {status}")

            body = resp_json.get("body", {})
            self.access_token = body.get("access_token")
            new_refresh_token = body.get("refresh_token")

            # Update refresh token if it changed
            if new_refresh_token and new_refresh_token != refresh_token:
                logger.info("Refresh token updated")
                self.config.update_env_file('WITHINGS_REFRESH_TOKEN', new_refresh_token)

            logger.info("Successfully authenticated with Withings")

        except Exception as e:
            logger.error(f"Failed to authenticate with Withings: {str(e)}")
            raise

    def get_measurements(self, start_timestamp: int, end_timestamp: int) -> List[Dict]:
        """
        Get weight measurements for a specific time range

        Args:
            start_timestamp: Unix timestamp for start
            end_timestamp: Unix timestamp for end

        Returns:
            List of measurement dicts with 'timestamp', 'weight', and optionally 'height' and 'bmi' keys
        """
        try:
            logger.info(f"Fetching Withings measurements from {start_timestamp} to {end_timestamp}")

            params = {
                "action": "getmeas",
                "access_token": self.access_token,
                "meastype": 1,  # Weight
                "category": 1,  # Real measurements
                "startdate": start_timestamp,
                "enddate": end_timestamp,
            }

            response = requests.get(GETMEAS_URL, params=params, timeout=30)
            resp_json = response.json()

            status = resp_json.get("status")
            if status == 401:
                # Token expired, refresh and retry
                logger.warning("Access token expired, refreshing...")
                self._authenticate()
                params["access_token"] = self.access_token
                response = requests.get(GETMEAS_URL, params=params, timeout=30)
                resp_json = response.json()
                status = resp_json.get("status")

            if status != 0:
                logger.error(f"Withings API returned error status: {status}")
                raise Exception(f"Withings getmeas failed with status {status}")

            body = resp_json.get("body", {})
            measuregrps = body.get("measuregrps", [])

            results = []
            for group in measuregrps:
                # Get timestamp (Unix timestamp)
                timestamp_unix = group.get("date")
                if timestamp_unix:
                    timestamp = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
                else:
                    continue

                # Parse measures
                weight_kg = None
                height_m = None

                for measure in group.get("measures", []):
                    measure_type = measure.get("type")
                    value = measure.get("value")
                    unit = measure.get("unit")

                    if value is None or unit is None:
                        continue

                    # Calculate actual value
                    actual_value = value * (10 ** unit)

                    if measure_type == 1:  # Weight in kg
                        weight_kg = actual_value
                    elif measure_type == 4:  # Height in meters
                        height_m = actual_value

                # Only add if we have weight data
                if weight_kg is not None:
                    measurement = {
                        'timestamp': timestamp,
                        'weight': weight_kg
                    }

                    # Calculate BMI if we have both weight and height
                    if height_m is not None and height_m > 0:
                        bmi = weight_kg / (height_m ** 2)
                        measurement['bmi'] = bmi
                        measurement['height'] = height_m
                        logger.debug(f"Found measurement: {weight_kg}kg, height {height_m}m, BMI {bmi:.2f} at {timestamp}")
                    else:
                        logger.debug(f"Found measurement: {weight_kg}kg at {timestamp}")

                    results.append(measurement)

            logger.info(f"Retrieved {len(results)} weight measurements")
            return results

        except Exception as e:
            logger.error(f"Error fetching Withings measurements: {str(e)}")
            raise

    def get_recent_measurements(self, days: int = 7) -> List[Dict]:
        """
        Get weight measurements from the last N days

        Args:
            days: Number of days to look back

        Returns:
            List of measurement dicts
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        return self.get_measurements(
            start_timestamp=int(start_time.timestamp()),
            end_timestamp=int(end_time.timestamp())
        )

    def subscribe_webhook(self, callback_url: str) -> bool:
        """
        Subscribe to Withings webhook notifications

        Args:
            callback_url: Your public HTTPS URL (e.g., from ngrok)

        Returns:
            True if successful
        """
        try:
            logger.info(f"Subscribing to Withings webhook at {callback_url}")

            params = {
                "action": "subscribe",
                "access_token": self.access_token,
                "callbackurl": callback_url,
                "appli": 1,  # Weight
            }

            response = requests.post(NOTIFY_URL, params=params, timeout=30)
            resp_json = response.json()

            status = resp_json.get("status")
            if status != 0:
                logger.error(f"Withings webhook subscribe failed with status: {status}")
                raise Exception(f"Subscribe failed with status {status}")

            logger.info("Successfully subscribed to Withings webhook")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to webhook: {str(e)}")
            raise

    def list_webhooks(self) -> List[Dict]:
        """
        List all active webhook subscriptions

        Returns:
            List of webhook subscriptions
        """
        try:
            params = {
                "action": "list",
                "access_token": self.access_token,
                "appli": 1,
            }

            response = requests.post(NOTIFY_URL, params=params, timeout=30)
            resp_json = response.json()

            status = resp_json.get("status")
            if status != 0:
                logger.error(f"Withings webhook list failed with status: {status}")
                return []

            body = resp_json.get("body", {})
            profiles = body.get("profiles", [])
            return profiles

        except Exception as e:
            logger.error(f"Failed to list webhooks: {str(e)}")
            return []

    def unsubscribe_webhook(self, callback_url: str) -> bool:
        """
        Unsubscribe from webhook notifications

        Args:
            callback_url: The callback URL to unsubscribe

        Returns:
            True if successful
        """
        try:
            logger.info(f"Unsubscribing from webhook: {callback_url}")

            params = {
                "action": "revoke",
                "access_token": self.access_token,
                "callbackurl": callback_url,
                "appli": 1,
            }

            response = requests.post(NOTIFY_URL, params=params, timeout=30)
            resp_json = response.json()

            status = resp_json.get("status")
            if status != 0:
                logger.error(f"Withings webhook revoke failed with status: {status}")
                raise Exception(f"Revoke failed with status {status}")

            logger.info("Successfully unsubscribed from webhook")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe from webhook: {str(e)}")
            raise
