"""
Garmin Connect weight writer via garmin-bridge.

Uses the shared garmin-bridge package for authenticated Garmin API access
with DI OAuth2 tokens and automatic refresh.
"""

import logging
from datetime import datetime

from garmin_bridge import upload_weight

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return True


def upload(
    weight_kg: float,
    timestamp: datetime,
    percent_fat: float | None = None,
    percent_hydration: float | None = None,
    bone_mass: float | None = None,
    muscle_mass: float | None = None,
    visceral_fat_rating: float | None = None,
) -> dict:
    if timestamp.tzinfo is None:
        return {
            "success": False,
            "action": "error",
            "reason": "timestamp must be timezone-aware",
            "timestamp_iso": None,
            "response": None,
        }

    timestamp_iso = timestamp.isoformat()

    return upload_weight(
        weight_kg=weight_kg,
        timestamp=timestamp_iso,
        percent_fat=percent_fat,
        percent_hydration=percent_hydration,
        bone_mass=bone_mass,
        muscle_mass=muscle_mass,
        visceral_fat_rating=visceral_fat_rating,
    )
