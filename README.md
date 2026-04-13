# Withings to Garmin Sync (local daemon)

Polls Withings for new weight measurements every 5 minutes and uploads them to
Garmin Connect via a headless-browser subprocess. Runs on the Ziggy box under
Windows Task Scheduler.

> **History:** this project was originally an AWS Lambda + API Gateway + DynamoDB
> stack that received Withings webhooks in real time. In March 2026 Garmin
> deployed Cloudflare TLS fingerprinting that blocked the `garth` Python library
> the Lambda used, and the sync silently broke for weeks. The 2026-04-13
> rewrite moved everything local: the Withings half (which was never broken)
> stayed put, and the Garmin half now subprocesses out to
> [`garmin-connect-mcp`](https://github.com/robburke/garmin-connect-mcp), which
> routes API calls through a Playwright Chromium instance and inherits a real
> browser TLS fingerprint. See the project's `decisions/ADR-001` in the
> Obsidian vault under `Projects/Withings Sync Revival/` for the full
> rationale.

## Architecture

```
   ┌──────────────────┐
   │  Withings scale  │
   └────────┬─────────┘
            │ (cloud sync)
            ▼
   ┌──────────────────┐
   │   Withings API   │
   └────────┬─────────┘
            │ polled every 5 min via refresh token
            ▼
   ┌────────────────────────────────────────┐
   │     Ziggy box (Windows, 24/7)          │
   │                                        │
   │  sync_daemon.py                        │
   │   - Config (.env)                      │
   │   - WithingsClient (raw requests)      │
   │   - SyncService                        │
   │   - garmin_writer.upload_weight()      │
   │       │                                │
   │       ▼ subprocess                     │
   │  npx tsx upload-weight-cli.ts          │
   │   (in E:\projects\garmin-connect-mcp)  │
   └─────────────────┼──────────────────────┘
                     │ HTTPS (real Chrome TLS fingerprint)
                     ▼
         ┌──────────────────────┐
         │  Garmin Connect API  │
         │  (behind Cloudflare) │
         └──────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `sync_daemon.py` | Main entry point. Reads watermark, polls Withings, uploads new weights, advances watermark. |
| `sync_service.py` | Orchestration: fetch -> dedup -> upload. |
| `withings_client.py` | Raw-requests Withings client. Handles refresh-token rotation. |
| `garmin_writer.py` | Subprocess shim to `upload-weight-cli.ts` in garmin-connect-mcp. |
| `deduplicator.py` | In-batch dedup as defense-in-depth (the watermark is the primary mechanism). |
| `config.py` | Loads `.env`, validates required Withings keys. |
| `webhook_manager.py` | Legacy. Used to subscribe/list/unsubscribe Withings webhooks. The local daemon doesn't use webhooks but this script is kept for one-shot ops. |
| `reauth_withings.py` | Run when the refresh token in `.env` stops working. Walks through OAuth2. |
| `run_withings_sync.bat` | Windows Task Scheduler wrapper. |
| `last_sync_timestamp.json` | Watermark of the most recent successfully synced measurement. Auto-written by the daemon; do not hand-edit unless backfilling. |
| `sync.log` | Local log file. Rotation is the operating system's problem for now. |

## First-time setup

1. Install Python 3.14+ and create a venv:
   ```
   C:\Python314\python.exe -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Populate `.env`:
   ```
   WITHINGS_CLIENT_ID=...
   WITHINGS_CLIENT_SECRET=...
   WITHINGS_REFRESH_TOKEN=...
   WITHINGS_CALLBACK_URI=http://localhost:5000/callback
   ```

3. Make sure `garmin-connect-mcp` exists at `E:\projects\garmin-connect-mcp` and
   has a fresh session at `~/.garmin-connect-mcp/session.json`. If not, see
   that project's README for the Playwright login flow.

4. Test:
   ```
   venv\Scripts\python.exe sync_daemon.py --dry
   ```

5. Schedule via Windows Task Scheduler to run `run_withings_sync.bat` every
   5 minutes.

## Operational notes

- **Watermark behaviour:** the daemon only advances `last_sync_timestamp.json`
  if there were zero errors. If a run partially fails, the next run retries
  from the same point. This means a stuck error will keep retrying the same
  measurement until either the error clears or you manually edit the watermark.
- **Withings token refresh:** the refresh token rotates on every successful
  auth. The daemon writes the new token back to `.env` automatically (see
  `withings_client._authenticate` -> `config.update_env_file`).
- **Garmin session expiry:** the `garmin-connect-mcp` Playwright session
  expires periodically (Cloudflare cookie TTL). Symptom: the daemon logs
  401 errors from `upload-weight-cli`. Fix: re-run the Playwright login
  flow in `garmin-connect-mcp` to refresh `~/.garmin-connect-mcp/session.json`.
  This is currently manual.
- **Backfill / replay:** use `--since 2026-04-10T00:00:00+00:00` to override
  the watermark for backfills. The daemon will fetch all measurements newer
  than that timestamp, upload them, and advance the watermark to the newest one.
- **Withings rate limits:** if you call `webhook_manager.py` or hit `_authenticate()`
  too rapidly, Withings returns status 601 ("Same arguments in less than 10
  seconds"). Wait ~70s and retry.

## Withings webhook -- legacy

The pre-2026-04-13 architecture used a Withings webhook pointed at the Lambda's
API Gateway URL. After cutover the webhook was unsubscribed via:

```
venv\Scripts\python.exe webhook_manager.py unsubscribe https://j7ebm5kb9l.execute-api.ca-central-1.amazonaws.com/prod/webhook/withings
```

The local daemon does not need a webhook -- 5-minute polling is sufficient
for weight measurements.

## Cost

$0/month after the AWS stack is deleted. The Ziggy box is on regardless, so
the marginal cost of running this is electrons and disk space.

## License

MIT.
