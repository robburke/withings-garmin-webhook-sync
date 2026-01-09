"""
Deduplicator - Logic for detecting duplicate weight measurements
Uses timestamp + weight value matching with tolerance
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict

logger = logging.getLogger(__name__)


class Deduplicator:
    """Handles duplicate detection logic"""

    # Timestamp tolerance: consider measurements within ±2 minutes as same time
    TIMESTAMP_TOLERANCE_MINUTES = 2

    # Weight tolerance: weights within 0.1kg considered same (accounts for rounding)
    WEIGHT_TOLERANCE_KG = 0.1

    def __init__(self, timestamp_tolerance_minutes: int = None, weight_tolerance_kg: float = None):
        """
        Initialize deduplicator

        Args:
            timestamp_tolerance_minutes: Custom timestamp tolerance (default: 2 minutes)
            weight_tolerance_kg: Custom weight tolerance (default: 0.1kg)
        """
        if timestamp_tolerance_minutes is not None:
            self.TIMESTAMP_TOLERANCE_MINUTES = timestamp_tolerance_minutes
        if weight_tolerance_kg is not None:
            self.WEIGHT_TOLERANCE_KG = weight_tolerance_kg

        logger.info(
            f"Deduplicator configured with timestamp tolerance: ±{self.TIMESTAMP_TOLERANCE_MINUTES}min, "
            f"weight tolerance: ±{self.WEIGHT_TOLERANCE_KG}kg"
        )

    def is_duplicate(self, measurement: Dict, existing_measurements: List[Dict]) -> bool:
        """
        Check if a measurement is a duplicate of any existing measurement

        Args:
            measurement: Dict with 'timestamp' and 'weight' keys
            existing_measurements: List of existing measurements

        Returns:
            True if duplicate found
        """
        new_timestamp = measurement['timestamp']
        new_weight = measurement['weight']

        for existing in existing_measurements:
            existing_timestamp = existing['timestamp']
            existing_weight = existing['weight']

            # Check if timestamps are within tolerance
            time_diff = abs((new_timestamp - existing_timestamp).total_seconds() / 60)
            if time_diff <= self.TIMESTAMP_TOLERANCE_MINUTES:
                # Timestamps match, now check weight
                weight_diff = abs(new_weight - existing_weight)
                if weight_diff <= self.WEIGHT_TOLERANCE_KG:
                    logger.debug(
                        f"Duplicate found: {new_weight}kg at {new_timestamp} "
                        f"matches {existing_weight}kg at {existing_timestamp} "
                        f"(time_diff: {time_diff:.1f}min, weight_diff: {weight_diff:.2f}kg)"
                    )
                    return True

        return False

    def filter_duplicates(
        self,
        new_measurements: List[Dict],
        existing_measurements: List[Dict]
    ) -> List[Dict]:
        """
        Filter out duplicate measurements

        Args:
            new_measurements: List of new measurements to check
            existing_measurements: List of existing measurements to compare against

        Returns:
            List of measurements that are NOT duplicates
        """
        logger.info(
            f"Filtering duplicates from {len(new_measurements)} new measurements "
            f"against {len(existing_measurements)} existing measurements"
        )

        unique_measurements = []

        for measurement in new_measurements:
            if not self.is_duplicate(measurement, existing_measurements):
                unique_measurements.append(measurement)
            else:
                logger.info(
                    f"Skipping duplicate: {measurement['weight']}kg at "
                    f"{measurement['timestamp'].isoformat()}"
                )

        logger.info(f"Found {len(unique_measurements)} unique measurements")

        # Sort by timestamp (oldest first)
        unique_measurements.sort(key=lambda x: x['timestamp'])

        return unique_measurements

    def find_duplicates_in_list(self, measurements: List[Dict]) -> List[tuple]:
        """
        Find duplicates within a single list of measurements

        Args:
            measurements: List of measurements

        Returns:
            List of tuples (index1, index2) indicating duplicate pairs
        """
        duplicates = []

        for i, m1 in enumerate(measurements):
            for j, m2 in enumerate(measurements[i + 1:], start=i + 1):
                time_diff = abs((m1['timestamp'] - m2['timestamp']).total_seconds() / 60)
                weight_diff = abs(m1['weight'] - m2['weight'])

                if (time_diff <= self.TIMESTAMP_TOLERANCE_MINUTES and
                        weight_diff <= self.WEIGHT_TOLERANCE_KG):
                    duplicates.append((i, j))

        return duplicates
