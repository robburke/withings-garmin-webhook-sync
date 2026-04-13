"""
Withings -> Garmin sync daemon.

Polled entry point invoked by Windows Task Scheduler every 5 minutes.
Reads last_sync_timestamp.json, asks Withings for measurements newer
than that, uploads each to Garmin Connect via upload-weight-cli, and
advances the watermark on success.

Usage:
    python sync_daemon.py            # live run
    python sync_daemon.py --dry      # fetch and log, no Garmin writes
    python sync_daemon.py --since 2026-04-12T00:00:00+00:00   # override watermark for backfill

On a fresh install (no last_sync file), defaults to "1 hour ago" so the
first run picks up only very recent measurements rather than backfilling
arbitrary history. Use --since to backfill explicitly.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import Config
from sync_service import SyncService

LAST_SYNC_FILE = Path(__file__).parent / "last_sync_timestamp.json"
LOG_FILE = Path(__file__).parent / "sync.log"
DEFAULT_LOOKBACK = timedelta(hours=1)


def setup_logging() -> None:
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    stream = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    stream.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(stream)


def load_last_sync() -> datetime:
    if not LAST_SYNC_FILE.exists():
        return datetime.now(timezone.utc) - DEFAULT_LOOKBACK
    try:
        with open(LAST_SYNC_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("last_sync_timestamp")
        if not ts:
            return datetime.now(timezone.utc) - DEFAULT_LOOKBACK
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Could not parse %s, defaulting to %s ago: %s",
            LAST_SYNC_FILE, DEFAULT_LOOKBACK, e,
        )
        return datetime.now(timezone.utc) - DEFAULT_LOOKBACK


def save_last_sync(ts: datetime) -> None:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    payload = {
        "last_sync_timestamp": ts.isoformat(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(LAST_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Withings -> Garmin sync daemon")
    parser.add_argument("--dry", action="store_true", help="dry run -- fetch but do not write to Garmin")
    parser.add_argument("--since", help="ISO 8601 watermark override (e.g. 2026-04-12T00:00:00+00:00)")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("sync_daemon")
    logger.info("=" * 60)
    logger.info("sync_daemon starting (dry=%s)", args.dry)

    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.error("Invalid --since value: %s", e)
            return 1
        logger.info("Watermark override: %s", since.isoformat())
    else:
        since = load_last_sync()
        logger.info("Loaded watermark: %s", since.isoformat())

    try:
        config = Config()
        service = SyncService(config)
        result = service.sync_since(since, dry_run=args.dry)
    except Exception as e:
        logger.error("Sync run failed: %s", e, exc_info=True)
        return 1

    logger.info(
        "Sync complete: synced=%d errors=%d high_water=%s",
        result["synced"], result["errors"], result["high_water_mark"].isoformat(),
    )

    # Only advance the watermark if there were no errors. If something failed
    # mid-batch we want the next run to retry from the same point.
    if not args.dry and result["errors"] == 0 and result["high_water_mark"] > since:
        save_last_sync(result["high_water_mark"])
        logger.info("Persisted new watermark: %s", result["high_water_mark"].isoformat())
    elif args.dry:
        logger.info("Dry run -- not persisting watermark")
    elif result["errors"] > 0:
        logger.warning("Errors present -- watermark NOT advanced; next run will retry")

    return 0 if result["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
