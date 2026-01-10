"""
Sync Service - Business logic for syncing weight data from Withings to Garmin
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from withings_client import WithingsClient
from garmin_client import GarminClient
from deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class SyncService:
    """Handles the syncing logic between Withings and Garmin"""

    MAX_ENTRIES_PER_SYNC = 5  # Safety limit

    def __init__(self, config):
        self.config = config
        self.withings = WithingsClient(config)
        self.garmin = GarminClient(config)
        self.deduplicator = Deduplicator()

    def sync_weights(self, user_id: str = None, start_date: int = None, end_date: int = None) -> Dict:
        """
        Sync weight measurements from Withings to Garmin

        Args:
            user_id: Withings user ID (optional, for webhook context)
            start_date: Unix timestamp for start date (optional)
            end_date: Unix timestamp for end date (optional)

        Returns:
            Dict with sync results
        """
        try:
            # If specific date range provided, use it; otherwise get last 7 days
            if start_date and end_date:
                withings_measurements = self.withings.get_measurements(start_date, end_date)
            else:
                # Default: get measurements from last 7 days
                withings_measurements = self.withings.get_recent_measurements(days=7)

            if not withings_measurements:
                logger.info("No new measurements found in Withings")
                return {'synced': 0, 'skipped': 0, 'message': 'No new measurements'}

            logger.info(f"Found {len(withings_measurements)} measurements from Withings")

            # Get recent Garmin weigh-ins for duplicate detection
            # Look back 30 days to be safe
            lookback_date = datetime.now() - timedelta(days=30)
            garmin_weights = self.garmin.get_weights(since=lookback_date)

            logger.info(f"Found {len(garmin_weights)} existing weights in Garmin")

            # Filter out duplicates
            new_measurements = self.deduplicator.filter_duplicates(
                withings_measurements,
                garmin_weights
            )

            if not new_measurements:
                logger.info("All measurements already exist in Garmin")
                return {
                    'synced': 0,
                    'skipped': len(withings_measurements),
                    'message': 'All measurements already synced'
                }

            # Apply safety limit
            if len(new_measurements) > self.MAX_ENTRIES_PER_SYNC:
                logger.warning(
                    f"Found {len(new_measurements)} new measurements, "
                    f"limiting to {self.MAX_ENTRIES_PER_SYNC} for safety"
                )
                new_measurements = new_measurements[:self.MAX_ENTRIES_PER_SYNC]

            # Sync to Garmin
            synced_count = 0
            for measurement in new_measurements:
                try:
                    # Pass BMI if available
                    bmi = measurement.get('bmi')

                    success = self.garmin.add_weight(
                        weight_kg=measurement['weight'],
                        timestamp=measurement['timestamp'],
                        bmi=bmi
                    )
                    if success:
                        synced_count += 1
                        bmi_str = f", BMI {bmi:.2f}" if bmi else ""
                        logger.info(
                            f"Synced weight: {measurement['weight']}kg{bmi_str} at "
                            f"{measurement['timestamp'].isoformat()}"
                        )
                except Exception as e:
                    logger.error(f"Failed to sync measurement: {str(e)}")
                    continue

            skipped = len(withings_measurements) - synced_count

            logger.info(f"Sync complete: {synced_count} synced, {skipped} skipped")

            return {
                'synced': synced_count,
                'skipped': skipped,
                'message': f'Successfully synced {synced_count} measurements'
            }

        except Exception as e:
            logger.error(f"Error during sync: {str(e)}", exc_info=True)
            raise

    def sync_recent_weights(self, days: int = 7) -> Dict:
        """
        Sync recent weights from the last N days

        Args:
            days: Number of days to look back

        Returns:
            Dict with sync results
        """
        logger.info(f"Starting manual sync for last {days} days")
        return self.sync_weights()
