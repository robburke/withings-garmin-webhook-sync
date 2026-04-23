# Withings to Garmin Sync (local daemon)

Polls Withings for new weight and body composition measurements every hour and
uploads them to Garmin Connect via
[garmin-bridge](https://github.com/robburke/garmin-bridge). Runs on the home
server under Windows Task Scheduler.

> **History:** this project was originally an AWS Lambda + API Gateway + DynamoDB
> stack that received Withings webhooks in real time. In March 2026 Garmin
> deployed Cloudflare TLS fingerprinting that blocked the `garth` Python library
> the Lambda used, and the sync silently broke for weeks. The 2026-04-13
> rewrite moved everything local with a subprocess shim to a Playwright-based
> bridge. The 2026-04-23 rewrite replaced that with
> [garmin-bridge](https://github.com/robburke/garmin-bridge), a shared Python
> package using `python-garminconnect` 0.3.3 and DI OAuth2 tokens (same auth
> as the Android app) with automatic refresh.

## Architecture

```
   +------------------+
   |  Withings scale  |
   +--------+---------+
            | (cloud sync)
            v
   +------------------+
   |   Withings API   |
   +--------+---------+
            | polled hourly via refresh token
            v
   +----------------------------------------+
   |     Home server (Windows, 24/7)        |
   |                                        |
   |  sync_daemon.py                        |
   |   - Config (.env)                      |
   |   - WithingsClient (raw requests)      |
   |     - weight, fat%, hydration%, bone   |
   |       mass, muscle mass, visceral fat  |
   |   - SyncService                        |
   |   - garmin_writer.upload()             |
   |       |                                |
   |       v                                |
   |  garmin-bridge (pip package)           |
   |   - DI OAuth2 tokens (auto-refresh)    |
   |   - curl_cffi TLS fingerprinting       |
   |   - File-locked singleton session      |
   +--------+-------------------------------+
            | HTTPS (DI Bearer token)
            v
   +------------------------+
   |  Garmin Connect API    |
   |  (connectapi.garmin.com)|
   +------------------------+
```

## Files

| File | Purpose |
|------|---------|
| `sync_daemon.py` | Main entry point. Reads watermark, polls Withings, uploads new weights, advances watermark. |
| `sync_service.py` | Orchestration: fetch, dedup, upload (with body composition). |
| `withings_client.py` | Raw-requests Withings client. Fetches weight + body comp. Handles refresh-token rotation. |
| `garmin_writer.py` | Thin wrapper around `garmin_bridge.upload_weight`. |
| `deduplicator.py` | In-batch dedup as defense-in-depth (the watermark is the primary mechanism). |
| `config.py` | Loads `.env`, validates required Withings keys. |
| `webhook_manager.py` | Legacy. Used to subscribe/list/unsubscribe Withings webhooks. Kept for one-shot ops. |
| `reauth_withings.py` | Run when the Withings refresh token in `.env` stops working. Walks through OAuth2. |
| `run_withings_sync.ps1` | Windows Task Scheduler wrapper (silent, no console flash). |
| `last_sync_timestamp.json` | Watermark of the most recent successfully synced measurement. Auto-written by the daemon. |
| `sync.log` | Local log file. |

## First-time setup

1. Install Python 3.12+ and create a venv:
   ```
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Populate `.env`:
   ```
   WITHINGS_CLIENT_ID=...
   WITHINGS_CLIENT_SECRET=...
   WITHINGS_REFRESH_TOKEN=...
   WITHINGS_CALLBACK_URI=http://localhost:5000/callback
   GARMIN_EMAIL=...
   GARMIN_PASSWORD=...
   ```

3. Set up garmin-bridge (one-time, requires MFA):
   ```
   pip install -e path/to/garmin-bridge
   python -m garmin_bridge
   ```
   Tokens are saved to `~/.garminconnect/` and auto-refresh via DI OAuth2
   refresh tokens (same mechanism as the Garmin Android app).

4. Test:
   ```
   venv\Scripts\python.exe sync_daemon.py --dry
   ```

5. Schedule via Windows Task Scheduler to run `run_withings_sync.ps1` every
   hour.

## Body composition

As of 2026-04-23, the daemon fetches all available body composition fields
from Withings and uploads them to Garmin alongside weight:

- Fat percentage
- Hydration percentage
- Bone mass (kg)
- Muscle mass (kg)
- Visceral fat index

If body composition data is present, garmin-bridge uses the FIT-file upload
path (`add_body_composition`). If only weight is available, it uses the
simpler JSON path (`add_weigh_in`).

## Operational notes

- **Watermark behaviour:** the daemon only advances `last_sync_timestamp.json`
  if there were zero errors. If a run partially fails, the next run retries
  from the same point.
- **Withings token refresh:** the refresh token rotates on every successful
  auth. The daemon writes the new token back to `.env` automatically.
- **Garmin token refresh:** garmin-bridge uses DI OAuth2 refresh tokens which
  are long-lived (weeks/months). Token refresh is automatic and transparent.
  If refresh eventually fails, garmin-bridge writes a task to the local inbox
  prompting re-authentication via `python -m garmin_bridge`.
- **Backfill / replay:** use `--since 2026-04-10T00:00:00+00:00` to override
  the watermark. The daemon fetches all measurements newer than that timestamp,
  uploads them (capped at 5 per run for safety), and advances the watermark.
  Run multiple times to drain large backlogs.
- **Withings rate limits:** if you hit `_authenticate()` too rapidly, Withings
  returns status 601. Wait ~70s and retry.

## Cost

$0/month. The home server is on regardless.

## License

MIT.
