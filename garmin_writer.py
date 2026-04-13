"""
Garmin Connect weight writer.

Calls the upload-weight-cli.ts in garmin-connect-mcp via subprocess to
record a weigh-in in Garmin Connect. This indirects the call through a
headless Playwright Chromium instance so we inherit a real Chrome TLS
fingerprint and bypass Cloudflare's bot blocking (the wall that broke
the original garth-based path in March 2026).

Mirrors the subprocess pattern used in strava-tagger/garmin_writer.py.
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

GARMIN_MCP_DIR = Path(r"E:\projects\garmin-connect-mcp")
UPLOAD_WEIGHT_CLI = GARMIN_MCP_DIR / "src" / "upload-weight-cli.ts"


def is_enabled() -> bool:
    """Garmin upload is enabled when the CLI script exists on disk."""
    return UPLOAD_WEIGHT_CLI.exists()


def upload_weight(weight_kg: float, timestamp: datetime, unit_key: str = "kg") -> dict:
    """Record a weigh-in in Garmin Connect.

    Args:
        weight_kg: weight value (in the unit_key unit)
        timestamp: datetime of the measurement (must be timezone-aware)
        unit_key: "kg" or "lbs" (defaults to kg)

    Returns:
        Dict with:
            success: bool
            action: "uploaded" | "skipped" | "error"
            reason: human-readable explanation
            timestamp_iso: the ISO timestamp passed to the CLI
            response: the parsed CLI JSON output (on success), or None
    """
    if not is_enabled():
        return {
            "success": False,
            "action": "skipped",
            "reason": f"upload-weight-cli not found at {UPLOAD_WEIGHT_CLI}",
            "timestamp_iso": None,
            "response": None,
        }

    if timestamp.tzinfo is None:
        return {
            "success": False,
            "action": "error",
            "reason": "timestamp must be timezone-aware",
            "timestamp_iso": None,
            "response": None,
        }

    timestamp_iso = timestamp.isoformat()

    cmd = [
        "npx",
        "tsx",
        str(UPLOAD_WEIGHT_CLI),
        f"{weight_kg}",
        timestamp_iso,
        unit_key,
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(GARMIN_MCP_DIR),
            capture_output=True,
            text=True,
            timeout=180,
            shell=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "action": "error",
            "reason": "upload-weight-cli timed out after 180s",
            "timestamp_iso": timestamp_iso,
            "response": None,
        }
    except Exception as e:
        return {
            "success": False,
            "action": "error",
            "reason": f"failed to spawn upload-weight-cli: {e}",
            "timestamp_iso": timestamp_iso,
            "response": None,
        }

    if result.returncode != 0:
        stderr_snippet = (result.stderr or "").strip()[:400]
        return {
            "success": False,
            "action": "error",
            "reason": f"upload-weight-cli exit {result.returncode}: {stderr_snippet}",
            "timestamp_iso": timestamp_iso,
            "response": None,
        }

    parsed = None
    try:
        parsed = json.loads(result.stdout)
    except Exception:
        # Garmin returns 204 on success, but the CLI still wraps it in JSON.
        # If parse fails, treat as soft success but log the raw output.
        logger.warning("upload-weight-cli stdout was not valid JSON: %r", result.stdout[:200])

    return {
        "success": True,
        "action": "uploaded",
        "reason": f"uploaded {weight_kg} {unit_key} at {timestamp_iso}",
        "timestamp_iso": timestamp_iso,
        "response": parsed,
    }
