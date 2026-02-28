"""
Garmin Connect API Client
Handles authentication and data upload to Garmin Connect
Supports both local file-based sessions and DynamoDB storage for Lambda
"""
import logging
import os
import json
import tempfile
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from garminconnect import Garmin
import garth

logger = logging.getLogger(__name__)


def is_lambda_environment() -> bool:
    """Check if running in AWS Lambda"""
    return bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))


class GarminClient:
    """Wrapper for Garmin Connect API"""

    def __init__(self, config):
        self.config = config
        self.client = None
        self.is_lambda = is_lambda_environment()

        if self.is_lambda:
            # Lambda: use temp dir for garth session files
            self.session_dir = os.path.join(tempfile.gettempdir(), '.garmin_session')
        else:
            # Local: use project directory
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

            # In Lambda, try to restore session from DynamoDB first
            if self.is_lambda:
                self._restore_session_from_dynamodb()

            # Try to load existing session
            try:
                garth.resume(self.session_dir)
                logger.info("Loaded existing Garmin session")

                # CRITICAL: Update User-Agent to work with Garmin's Nov 2024 API changes
                # See: https://github.com/matin/garth/issues/73
                garth.client.sess.headers['User-Agent'] = 'GCM-iOS-5.7.2.1'

                self.client = Garmin()
                # Assign the garth client to ensure OAuth1 token is available for uploads
                self.client.garth = garth.client
                # Verify session is still valid by trying to use it
                try:
                    # Try a simple API call to verify the session works
                    self.client.get_full_name()
                    logger.info("Successfully authenticated with Garmin Connect (using saved session)")
                    # Persist back to DynamoDB in case garth auto-refreshed the OAuth2 tokens
                    # (garth refreshes in memory but doesn't trigger _save_session_to_dynamodb)
                    if self.is_lambda:
                        garth.save(self.session_dir)  # write refreshed tokens to /tmp
                        self._save_session_to_dynamodb()  # then persist to DynamoDB
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

                # CRITICAL: Set User-Agent after login too (Garmin Nov 2024 API change)
                garth.client.sess.headers['User-Agent'] = 'GCM-iOS-5.7.2.1'

                garth.save(self.session_dir)
                logger.info("Successfully authenticated with Garmin Connect (via garth)")

                # In Lambda, persist session to DynamoDB
                if self.is_lambda:
                    self._save_session_to_dynamodb()

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

    def _restore_session_from_dynamodb(self):
        """Restore Garmin session files from DynamoDB to temp directory"""
        try:
            import boto3

            table_name = os.environ.get('TOKEN_TABLE_NAME')
            if not table_name:
                logger.warning("TOKEN_TABLE_NAME not set, cannot restore session from DynamoDB")
                return

            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={'token_type': 'garmin_session'})

            if 'Item' in response:
                session_data = response['Item'].get('session_data')
                if session_data:
                    # session_data contains the serialized garth tokens
                    data = json.loads(session_data)

                    # Write the OAuth tokens to files that garth expects
                    os.makedirs(self.session_dir, exist_ok=True)

                    if 'oauth1_token' in data:
                        with open(os.path.join(self.session_dir, 'oauth1_token.json'), 'w') as f:
                            json.dump(data['oauth1_token'], f)

                    if 'oauth2_token' in data:
                        with open(os.path.join(self.session_dir, 'oauth2_token.json'), 'w') as f:
                            json.dump(data['oauth2_token'], f)

                    logger.info("Restored Garmin session from DynamoDB")
            else:
                logger.info("No Garmin session found in DynamoDB")

        except Exception as e:
            logger.warning(f"Failed to restore Garmin session from DynamoDB: {e}")

    def _save_session_to_dynamodb(self):
        """Save Garmin session files from temp directory to DynamoDB"""
        try:
            import boto3

            table_name = os.environ.get('TOKEN_TABLE_NAME')
            if not table_name:
                logger.warning("TOKEN_TABLE_NAME not set, cannot save session to DynamoDB")
                return

            # Read the OAuth token files that garth saved
            session_data = {}

            oauth1_path = os.path.join(self.session_dir, 'oauth1_token.json')
            if os.path.exists(oauth1_path):
                with open(oauth1_path, 'r') as f:
                    session_data['oauth1_token'] = json.load(f)

            oauth2_path = os.path.join(self.session_dir, 'oauth2_token.json')
            if os.path.exists(oauth2_path):
                with open(oauth2_path, 'r') as f:
                    session_data['oauth2_token'] = json.load(f)

            if session_data:
                dynamodb = boto3.resource('dynamodb')
                table = dynamodb.Table(table_name)

                table.put_item(Item={
                    'token_type': 'garmin_session',
                    'session_data': json.dumps(session_data),
                    'updated_at': int(datetime.now().timestamp())
                })

                logger.info("Saved Garmin session to DynamoDB")

        except Exception as e:
            logger.error(f"Failed to save Garmin session to DynamoDB: {e}")

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
            timestamp: Timestamp of the measurement (should be timezone-aware UTC)
            bmi: Body Mass Index (optional, ignored)

        Returns:
            True if successful
        """
        try:
            import io
            from fit_encoder import FitEncoderWeight

            logger.info(f"Creating FIT file for weight: {weight_kg}kg at {timestamp.isoformat()}")

            # Convert UTC timestamp to local time for FIT file
            # FIT encoder uses time.mktime() which expects local time
            local_timestamp = timestamp.astimezone()
            logger.info(f"Converted to local time: {local_timestamp.isoformat()}")

            # Create FIT encoder exactly like withings-sync
            fit = FitEncoderWeight()
            fit.write_file_info()
            fit.write_file_creator()
            fit.write_device_info(timestamp=local_timestamp)
            fit.write_weight_scale(
                timestamp=local_timestamp,
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
            response = garth.client.upload(fit_file)

            # Log the upload response for debugging
            logger.info(f"Garmin upload response: {response}")

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
