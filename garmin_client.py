"""
Garmin Connect API Client
Handles authentication and data upload to Garmin Connect
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from garminconnect import Garmin
import garth

logger = logging.getLogger(__name__)


class GarminClient:
    """Wrapper for Garmin Connect API"""

    def __init__(self, config):
        self.config = config
        self.client = None
        self.session_dir = os.path.join(os.path.dirname(__file__), '.garmin_session')
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Garmin Connect with session persistence"""
        try:
            email = self.config.get('GARMIN_EMAIL')
            password = self.config.get('GARMIN_PASSWORD')

            if not email or not password:
                raise ValueError("Garmin credentials not configured")

            # Create session directory if it doesn't exist
            os.makedirs(self.session_dir, exist_ok=True)

            # Try to load existing session
            try:
                garth.resume(self.session_dir)
                logger.info("Loaded existing Garmin session")
                self.client = Garmin()
                # Assign the garth client to ensure OAuth1 token is available for uploads
                self.client.garth = garth.client
                # Verify session is still valid by trying to use it
                try:
                    # Try a simple API call to verify the session works
                    self.client.get_full_name()
                    logger.info("Successfully authenticated with Garmin Connect (using saved session)")
                    return
                except Exception as verify_error:
                    logger.info(f"Session exists but is invalid: {str(verify_error)}")
                    # Session is invalid, will re-login below
            except Exception as e:
                logger.info(f"No saved session found: {str(e)}")

            # No valid session, need to login
            logger.info(f"Authenticating with Garmin Connect as {email}")

            # Use garth directly for authentication to have better control
            try:
                garth.login(email, password)

                # Configure garth for all required domains
                garth.client.domain = "garmin.com"

                garth.save(self.session_dir)
                logger.info("Successfully authenticated with Garmin Connect (via garth)")
            except Exception as garth_error:
                logger.error(f"Garth login failed: {str(garth_error)}")
                raise

            # Now create Garmin client with authenticated session
            self.client = Garmin()
            # Assign the garth client to ensure OAuth1 token is available for uploads
            self.client.garth = garth.client

            # Verify login was successful and check capabilities
            try:
                profile = self.client.get_full_name()
                logger.info(f"Login verified. User: {profile}")

                # Log garth session info for debugging
                logger.debug(f"Garth client domain: {garth.client.domain if hasattr(garth, 'client') else 'N/A'}")
            except Exception as verify_error:
                logger.error(f"Login verification failed: {str(verify_error)}")
                raise

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
                    # get_weigh_ins requires both startdate and enddate
                    weight_data = self.client.get_weigh_ins(date_str, date_str)

                    if weight_data:
                        logger.info(f"Found weight data for {date_str}: {weight_data}")

                        # New API format has dailyWeightSummaries
                        if 'dailyWeightSummaries' in weight_data:
                            for summary in weight_data['dailyWeightSummaries']:
                                # Each summary has allWeightMetrics array
                                if 'allWeightMetrics' in summary:
                                    for metric in summary['allWeightMetrics']:
                                        if 'weight' in metric:
                                            weight_grams = metric['weight']
                                            weight_kg = weight_grams / 1000.0

                                            # Parse timestamp (in milliseconds)
                                            if 'timestampGMT' in metric:
                                                timestamp = datetime.fromtimestamp(metric['timestampGMT'] / 1000, tz=timezone.utc)
                                            elif 'date' in metric:
                                                timestamp = datetime.fromtimestamp(metric['date'] / 1000, tz=timezone.utc)
                                            else:
                                                timestamp = current.replace(tzinfo=timezone.utc)

                                            weights.append({
                                                'timestamp': timestamp,
                                                'weight': weight_kg
                                            })

                                            logger.debug(f"Found weight: {weight_kg}kg at {timestamp}")
                        else:
                            # Fallback for old API format (just in case)
                            for entry in weight_data:
                                if 'weight' in entry:
                                    weight_grams = entry['weight']
                                    weight_kg = weight_grams / 1000.0

                                    # Parse timestamp
                                    if 'date' in entry:
                                        timestamp = datetime.fromisoformat(entry['date'].replace('Z', '+00:00'))
                                    elif 'timestampGMT' in entry:
                                        timestamp = datetime.fromtimestamp(entry['timestampGMT'] / 1000, tz=timezone.utc)
                                    else:
                                        timestamp = current.replace(tzinfo=timezone.utc)

                                    weights.append({
                                        'timestamp': timestamp,
                                        'weight': weight_kg
                                    })

                                    logger.debug(f"Found weight: {weight_kg}kg at {timestamp}")

                except Exception as e:
                    # Log the actual error - this might be why we can't read OR write weights!
                    logger.error(f"ERROR fetching weight for {date_str}: {type(e).__name__}: {str(e)}")

                current += timedelta(days=1)

            logger.info(f"Retrieved {len(weights)} weights from Garmin")
            return weights

        except Exception as e:
            logger.error(f"Error fetching Garmin weights: {str(e)}")
            raise

    def add_weight(self, weight_kg: float, timestamp: datetime, bmi: float = None) -> bool:
        """
        Add a weight measurement to Garmin Connect using FIT file upload
        (Using the exact same approach as withings-sync)

        Args:
            weight_kg: Weight in kilograms
            timestamp: Timestamp of the measurement (should be timezone-aware)
            bmi: Body Mass Index (optional, ignored)

        Returns:
            True if successful
        """
        try:
            import io
            from fit_encoder import FitEncoderWeight

            logger.info(f"Creating FIT file for weight: {weight_kg}kg at {timestamp.isoformat()}")

            # Create FIT encoder exactly like withings-sync
            fit = FitEncoderWeight()
            fit.write_file_info()
            fit.write_file_creator()
            fit.write_device_info(timestamp=timestamp)
            fit.write_weight_scale(
                timestamp=timestamp,
                weight=weight_kg,
                percent_fat=None,
                percent_hydration=None,
                visceral_fat_mass=None,
                bone_mass=None,
                muscle_mass=None,
                basal_met=None,
                active_met=None,
                physique_rating=None,
                metabolic_age=None,
                visceral_fat_rating=None,
                bmi=None
            )
            fit.finish()

            # Upload EXACTLY like withings-sync does in upload_file method
            fit_file = io.BytesIO(fit.getvalue())
            fit_file.name = "withings.fit"

            logger.info(f"Uploading FIT file to Garmin Connect ({len(fit.getvalue())} bytes)")

            # Use garth.client.upload() exactly like withings-sync
            garth.client.upload(fit_file)

            logger.info(f"Successfully uploaded weight to Garmin")
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
