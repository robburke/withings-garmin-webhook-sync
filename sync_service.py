"""
Sync Service - poll Withings for new weight measurements and upload them
to Garmin Connect via the upload-weight-cli subprocess.

This replaces the previous Lambda-style sync_service which dedup'd against
existing Garmin weigh-ins. We now use a local last_sync_timestamp file as
the primary watermark, and the Deduplicator as in-batch defense-in-depth
in case Withings ever returns the same measurement twice in one response.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from deduplicator import Deduplicator
from withings_client import WithingsClient
import garmin_writer

logger = logging.getLogger(__name__)


class SyncService:
    """Pull-from-Withings, push-to-Garmin orchestration."""

    MAX_ENTRIES_PER_SYNC = 5  # Safety limit

    def __init__(self, config):
        self.config = config
        self.withings = WithingsClient(config)
        self.deduplicator = Deduplicator()

    def sync_since(self, since: datetime, dry_run: bool = False) -> Dict:
        """Fetch Withings measurements newer than `since` and upload to Garmin.

        Args:
            since: timezone-aware datetime; only measurements strictly later are processed
            dry_run: if True, fetch and log but do not write to Garmin

        Returns:
            Dict with synced/skipped counts, processed measurements, and a high-water-mark
            timestamp the caller can persist as the new last_sync.
        """
        if since.tzinfo is None:
            raise ValueError("`since` must be timezone-aware")

        now = datetime.now(timezone.utc)
        start_ts = int(since.timestamp())
        end_ts = int(now.timestamp())

        logger.info(
            "Fetching Withings measurements from %s (%d) to %s (%d)",
            since.isoformat(), start_ts, now.isoformat(), end_ts,
        )

        measurements = self.withings.get_measurements(start_ts, end_ts)

        # Withings' getmeas can return measurements at the boundary; filter strictly later.
        new_measurements = [m for m in measurements if m["timestamp"] > since]

        # In-batch dedup (defense in depth)
        new_measurements = self.deduplicator.filter_duplicates(new_measurements, [])

        if not new_measurements:
            logger.info("No new measurements since %s", since.isoformat())
            return {
                "synced": 0,
                "skipped": 0,
                "errors": 0,
                "processed": [],
                "high_water_mark": since,
                "message": "no new measurements",
            }

        if len(new_measurements) > self.MAX_ENTRIES_PER_SYNC:
            logger.warning(
                "Found %d new measurements, limiting to %d for safety",
                len(new_measurements), self.MAX_ENTRIES_PER_SYNC,
            )
            new_measurements = new_measurements[: self.MAX_ENTRIES_PER_SYNC]

        synced = 0
        errors = 0
        processed = []
        high_water = since

        for m in new_measurements:
            ts = m["timestamp"]
            wt = m["weight"]

            if dry_run:
                logger.info("[dry-run] would upload %.2fkg at %s", wt, ts.isoformat())
                processed.append({"timestamp": ts.isoformat(), "weight": wt, "result": "dry-run"})
                if ts > high_water:
                    high_water = ts
                continue

            result = garmin_writer.upload_weight(weight_kg=wt, timestamp=ts)

            if result["success"]:
                synced += 1
                logger.info(
                    "Uploaded %.2fkg at %s -- %s", wt, ts.isoformat(), result["reason"],
                )
                if ts > high_water:
                    high_water = ts
            else:
                errors += 1
                logger.error(
                    "Failed to upload %.2fkg at %s: %s", wt, ts.isoformat(), result["reason"],
                )

            processed.append({
                "timestamp": ts.isoformat(),
                "weight": wt,
                "result": result["action"],
                "reason": result["reason"],
            })

        return {
            "synced": synced,
            "skipped": 0,
            "errors": errors,
            "processed": processed,
            "high_water_mark": high_water,
            "message": f"synced {synced}, errors {errors}",
        }
