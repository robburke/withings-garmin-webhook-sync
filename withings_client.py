"""
Withings API Client
Handles authentication and data retrieval from Withings
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict
from withings_api import WithingsAuth, WithingsApi
from withings_api.common import MeasureType

logger = logging.getLogger(__name__)


class WithingsClient:
    """Wrapper for Withings API"""

    def __init__(self, config):
        self.config = config
        self.api = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Withings API"""
        try:
            # For webhook setup, we need to go through OAuth flow once
            # After that, we can use refresh tokens

            client_id = self.config.get('WITHINGS_CLIENT_ID')
            client_secret = self.config.get('WITHINGS_CLIENT_SECRET')

            # Check if we have a refresh token saved
            refresh_token = self.config.get('WITHINGS_REFRESH_TOKEN')

            if refresh_token:
                logger.info("Authenticating with Withings using refresh token")
                auth = WithingsAuth(
                    client_id=client_id,
                    consumer_secret=client_secret,
                    callback_uri=self.config.get('WITHINGS_CALLBACK_URI', 'http://localhost:5000/callback')
                )

                # Use refresh token to get new credentials
                credentials = auth.refresh_token(refresh_token)
                self.api = WithingsApi(credentials)

                # Save new refresh token if it changed
                if credentials.refresh_token != refresh_token:
                    logger.info("Refresh token updated")
                    # TODO: Implement token persistence
            else:
                logger.warning("No refresh token found. You need to complete OAuth flow first.")
                logger.warning("Run setup.py to complete initial authentication")
                raise ValueError("No refresh token configured. Run initial setup first.")

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
            List of measurement dicts with 'timestamp' and 'weight' keys
        """
        try:
            logger.info(f"Fetching Withings measurements from {start_timestamp} to {end_timestamp}")

            # Get weight measurements
            measurements = self.api.measure_get_meas(
                startdate=start_timestamp,
                enddate=end_timestamp,
                meastype=MeasureType.WEIGHT
            )

            results = []
            for measure_group in measurements.measuregrps:
                # Each measure group has a date and multiple measures
                timestamp = datetime.fromtimestamp(measure_group.date)

                # Find weight measurement
                for measure in measure_group.measures:
                    if measure.type == MeasureType.WEIGHT:
                        # Withings stores weight with a power-of-10 multiplier
                        weight_kg = measure.value * (10 ** measure.unit)

                        results.append({
                            'timestamp': timestamp,
                            'weight': weight_kg
                        })
                        logger.debug(f"Found measurement: {weight_kg}kg at {timestamp}")

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

            # Subscribe to weight notifications (appli=1)
            self.api.notify_subscribe(
                callbackurl=callback_url,
                appli=1  # 1 = weight
            )

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
            result = self.api.notify_list()
            return result.profiles if hasattr(result, 'profiles') else []
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

            self.api.notify_revoke(
                callbackurl=callback_url,
                appli=1
            )

            logger.info("Successfully unsubscribed from webhook")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe from webhook: {str(e)}")
            raise
