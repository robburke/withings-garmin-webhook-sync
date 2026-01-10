# Claude Development Notes

## Project Overview
This is a webhook-based sync service that automatically transfers weight measurements from Withings scales to Garmin Connect in real-time.

## Key Learnings & Implementation Details

### Critical Dependencies
- **garminconnect**: Use version 0.2.19 or later. Earlier versions have compatibility issues with the Garmin API.
- **garth**: Use version 0.5.1 or later for proper OAuth token handling.
- **withings-api**: Use version 2.4.0 or later. Older versions have Pydantic compatibility issues.

### Timezone Handling
The application deals with timezones in three places:

1. **Withings Client**: Returns timezone-aware UTC timestamps
   - Uses `datetime.fromtimestamp(unix_ts, tz=timezone.utc)`

2. **Garmin Client**: Must also return timezone-aware UTC timestamps
   - Critical: When parsing Garmin weight data, use `datetime.fromtimestamp(ts/1000, tz=timezone.utc)`
   - Without timezone info, comparison operations will fail with "can't subtract offset-naive and offset-aware datetimes"

3. **FIT File Generation**: Requires local timezone
   - The `fit_encoder.py` uses `time.mktime()` which expects local time
   - Before creating FIT files, convert UTC to local: `local_timestamp = timestamp.astimezone()`
   - This ensures weights appear with correct local time in Garmin Connect

### Authentication Flow

#### Withings OAuth2
- Uses refresh token flow (tokens stored in .env)
- Tokens auto-refresh when expired
- Initial setup requires `reauth_withings.py` script

#### Garmin OAuth1 + OAuth2
- Uses garth library which manages both OAuth1 and OAuth2 tokens
- Session data stored in `~/.garth/` directory
- OAuth2 tokens expire and are refreshed automatically using OAuth1 tokens
- Initial setup requires interactive login (email/password)

### Deduplication Strategy
The deduplicator prevents syncing the same weight multiple times:
- **Timestamp tolerance**: ±2 minutes
- **Weight tolerance**: ±0.1 kg
- Always fetches last 30 days of Garmin data for comparison
- Filters duplicates before syncing to avoid unnecessary API calls

### Webhook Implementation
- Withings sends POST requests when new measurements are available
- The app handles HEAD, GET, and POST to the webhook endpoint
- Uses ngrok or similar for local development exposure
- Logs all webhook activity to `sync.log`

### Logging Configuration
- Dual output: `sync.log` file + console (StreamHandler)
- Console output may be buffered in production - always check the log file
- All webhook processing is logged with timestamps and detailed info

### Common Issues & Solutions

#### Issue: "TimeZone.validate() takes 2 positional arguments but 3 were given"
**Solution**: Upgrade `withings-api` to 2.4.0 or later. This is a Pydantic v2 compatibility issue.

#### Issue: Weights appear with wrong time in Garmin
**Solution**: Convert UTC timestamps to local timezone before FIT file creation using `.astimezone()`

#### Issue: "can't subtract offset-naive and offset-aware datetimes"
**Solution**: Ensure all datetime objects created from timestamps include `tz=timezone.utc` parameter

#### Issue: Garmin authentication fails or expires
**Solution**:
- Delete `~/.garth/` directory
- Re-run initial setup with `garmin_client.py` login flow
- Ensure garth library is version 0.5.1+

### Development Workflow
1. Start Flask app: `python app.py`
2. Start ngrok: `ngrok http 5000`
3. Configure Withings webhook URL to ngrok URL + `/webhook/withings`
4. Monitor `sync.log` for real-time activity
5. Test with `/sync/manual?days=1` endpoint

### Production Deployment Notes
- Use a production WSGI server (gunicorn, uwsgi) instead of Flask dev server
- Set up proper webhook URL (not ngrok)
- Implement token refresh monitoring
- Consider health check endpoint (`/health`) for monitoring
- Rotate logs to prevent disk space issues

### File Structure
- `app.py` - Main Flask application with webhook endpoints
- `withings_client.py` - Withings API client with OAuth2 flow
- `garmin_client.py` - Garmin Connect client using garth library
- `sync_service.py` - Business logic for syncing weights
- `deduplicator.py` - Duplicate detection logic
- `fit_encoder.py` - FIT file format encoder (from withings-sync project)
- `config.py` - Configuration management (loads from .env)
- `.env` - Secrets and configuration (not in git)

### Testing Endpoints
- `GET /health` - Health check
- `POST /webhook/withings` - Withings webhook endpoint
- `POST /sync/manual?days=N` - Manual sync trigger for last N days
- `GET /test/garmin-weights?days=N` - Test Garmin weight fetching

### Security Considerations
- Never commit `.env` file
- Never commit `~/.garth/` tokens
- Withings refresh token should be treated as a secret
- Consider adding webhook signature verification for production
- Use HTTPS for webhook endpoints in production
