"""
Garmin Connect API Client
Handles authentication and data upload to Garmin Connect
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from garminconnect import Garmin

logger = logging.getLogger(__name__)


class GarminClient:
    """Wrapper for Garmin Connect API"""

    def __init__(self, config):
        self.config = config
        self.client = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Garmin Connect"""
        try:
            email = self.config.get('GARMIN_EMAIL')
            password = self.config.get('GARMIN_PASSWORD')

            if not email or not password:
                raise ValueError("Garmin credentials not configured")

            logger.info(f"Authenticating with Garmin Connect as {email}")

            self.client = Garmin(email, password)
            self.client.login()

            logger.info("Successfully authenticated with Garmin Connect")

        except Exception as e:
            logger.error(f"Failed to authenticate with Garmin: {str(e)}")
            raise

    def get_weights(self, since: datetime = None, until: datetime = None) -> List[Dict]:
        """
        Get weight data from Garmin Connect

        Args:
            since: Start date (default: 30 days ago)
            until: End date (default: today)

        Returns:
            List of weight dicts with 'timestamp' and 'weight' keys
        """
        try:
            if since is None:
                since = datetime.now() - timedelta(days=30)
            if until is None:
                until = datetime.now()

            logger.info(f"Fetching Garmin weights from {since.date()} to {until.date()}")

            weights = []

            # Garmin API requires fetching day by day
            current = since
            while current <= until:
                date_str = current.strftime('%Y-%m-%d')

                try:
                    # Get weight for this specific date
                    weight_data = self.client.get_weigh_ins(date_str)

                    if weight_data:
                        # weight_data is a list of weigh-ins for that day
                        for entry in weight_data:
                            # Parse the weight data
                            # Format varies, but typically has 'weight' in grams and 'timestamp'
                            if 'weight' in entry:
                                weight_grams = entry['weight']
                                weight_kg = weight_grams / 1000.0

                                # Parse timestamp
                                if 'date' in entry:
                                    timestamp = datetime.fromisoformat(entry['date'].replace('Z', '+00:00'))
                                elif 'timestampGMT' in entry:
                                    timestamp = datetime.fromtimestamp(entry['timestampGMT'] / 1000)
                                else:
                                    timestamp = current

                                weights.append({
                                    'timestamp': timestamp,
                                    'weight': weight_kg
                                })

                                logger.debug(f"Found weight: {weight_kg}kg at {timestamp}")

                except Exception as e:
                    # If no data for this day, that's ok
                    logger.debug(f"No weight data for {date_str}: {str(e)}")

                current += timedelta(days=1)

            logger.info(f"Retrieved {len(weights)} weights from Garmin")
            return weights

        except Exception as e:
            logger.error(f"Error fetching Garmin weights: {str(e)}")
            raise

    def add_weight(self, weight_kg: float, timestamp: datetime) -> bool:
        """
        Add a weight measurement to Garmin Connect

        Args:
            weight_kg: Weight in kilograms
            timestamp: Timestamp of the measurement

        Returns:
            True if successful
        """
        try:
            # Convert to grams (Garmin uses grams internally)
            weight_grams = int(weight_kg * 1000)

            # Format date for Garmin
            date_str = timestamp.strftime('%Y-%m-%d')
            time_str = timestamp.strftime('%H:%M:%S')

            logger.info(f"Adding weight to Garmin: {weight_kg}kg on {date_str} at {time_str}")

            # Use the add_weigh_in method
            # Note: The exact parameters may vary based on garminconnect version
            result = self.client.add_weigh_in(
                weight=weight_grams,
                unitKey='kg'
            )

            logger.info(f"Successfully added weight to Garmin: {result}")
            return True

        except Exception as e:
            logger.error(f"Failed to add weight to Garmin: {str(e)}")
            raise

    def test_connection(self) -> bool:
        """
        Test Garmin connection by fetching user profile

        Returns:
            True if connection is working
        """
        try:
            profile = self.client.get_full_name()
            logger.info(f"Garmin connection test successful. User: {profile}")
            return True
        except Exception as e:
            logger.error(f"Garmin connection test failed: {str(e)}")
            return False
