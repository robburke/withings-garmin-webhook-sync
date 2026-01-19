# Claude Development Notes

## Project Overview
This is a webhook-based sync service that automatically transfers weight measurements from Withings scales to Garmin Connect in real-time. It runs as a serverless AWS Lambda function - no local server or ngrok required.

## CRITICAL: Dependency Version Constraints

**This is the most important section. Read carefully before making any changes.**

There is a **pydantic version conflict** between the libraries:
- `withings-api==2.4.0` requires `pydantic<2.0.0`
- `garth>=0.5.0` requires `pydantic>=2.0.0`

**The solution is to pin garth to version 0.4.x:**

```
withings-api==2.4.0
garminconnect==0.2.19
garth>=0.4.46,<0.5.0
pydantic>=1.10.12,<2.0.0
```

**DO NOT upgrade garth to 0.5.x** - it will break the Lambda deployment with:
```
ImportError: cannot import name 'ValidationInfo' from 'pydantic'
```

### Garmin API User-Agent Fix (November 2024)

Garmin changed their API in November 2024 to reject requests with the old Mozilla user agent. The fix is to set:

```python
garth.client.sess.headers['User-Agent'] = 'GCM-iOS-5.7.2.1'
```

This must be done **after** `garth.resume()` but **before** making any API calls. Without this fix, uploads will silently fail (return empty `[]` response) and weights won't appear in Garmin Connect.

See: https://github.com/matin/garth/issues/73

## AWS Lambda Architecture

### Components
- **AWS Lambda** - Runs the sync logic (Python 3.12)
- **API Gateway** - HTTPS endpoints for webhooks
- **DynamoDB** - Stores Garmin OAuth session tokens
- **Secrets Manager** - Stores API credentials securely

### Endpoints
- `GET /health` - Health check
- `POST /webhook/withings` - Receives Withings notifications
- `HEAD /webhook/withings` - Withings subscription verification
- `GET /webhook/withings` - Withings subscription verification
- `POST /sync/manual` - Trigger manual sync for last 7 days

### Key Files
- `template.yaml` - AWS SAM infrastructure definition
- `lambda_handler.py` - Lambda entry point, routes API Gateway events
- `token_storage.py` - DynamoDB token persistence
- `garmin_client.py` - Garmin API client with User-Agent fix
- `config.py` - Auto-detects Lambda vs local environment

## Deployment

### Prerequisites
1. AWS CLI configured with credentials
2. AWS SAM CLI installed
3. Python 3.12

### Deploy Commands
```bash
sam build
sam deploy --no-confirm-changeset
```

### First-Time Setup

1. **Deploy the infrastructure:**
   ```bash
   sam build && sam deploy --guided
   ```

2. **Configure Secrets Manager** with your credentials:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id withings-garmin-secrets-prod \
     --secret-string file://secrets.json \
     --region ca-central-1
   ```

3. **Bootstrap Garmin session locally** (required for MFA):
   - Run `python bootstrap_garmin.py` locally
   - This authenticates with Garmin (handles MFA in browser)
   - Uploads session to DynamoDB for Lambda to use

4. **Subscribe Withings webhook:**
   ```bash
   python webhook_manager.py subscribe https://YOUR-API-GATEWAY-URL/prod/webhook/withings
   ```

## Timezone Handling

1. **Withings Client**: Returns timezone-aware UTC timestamps
   - Uses `datetime.fromtimestamp(unix_ts, tz=timezone.utc)`

2. **Garmin Client**: Must also return timezone-aware UTC timestamps
   - Use `datetime.fromtimestamp(ts/1000, tz=timezone.utc)`

3. **FIT File Generation**: Uses `time.mktime()` which expects local time
   - In Lambda, this is UTC (Lambda runs in UTC timezone)
   - Convert with `timestamp.astimezone()`

## Authentication Flow

### Withings OAuth2
- Refresh token stored in Secrets Manager
- Auto-refreshes when expired
- Lambda updates Secrets Manager with new tokens

### Garmin OAuth1 + OAuth2
- Session stored in DynamoDB (token_type: 'garmin_session')
- Contains both oauth1_token and oauth2_token JSON
- OAuth2 tokens auto-refresh using OAuth1 credentials
- **Initial setup requires local bootstrap** (MFA can't be handled in Lambda)

## Common Issues & Solutions

### Issue: Uploads succeed but weights don't appear in Garmin
**Cause**: Old User-Agent being rejected by Garmin API
**Solution**: Set `garth.client.sess.headers['User-Agent'] = 'GCM-iOS-5.7.2.1'`

### Issue: `ImportError: cannot import name 'ValidationInfo' from 'pydantic'`
**Cause**: garth 0.5.x requires pydantic v2, but withings-api requires pydantic v1
**Solution**: Pin `garth>=0.4.46,<0.5.0` and `pydantic>=1.10.12,<2.0.0`

### Issue: Garmin upload returns empty `[]` response
**Cause**: User-Agent not set correctly, Garmin silently rejecting requests
**Solution**: Ensure User-Agent fix is applied after garth.resume()

### Issue: Garmin MFA blocks Lambda authentication
**Cause**: Lambda can't handle interactive MFA browser flow
**Solution**: Bootstrap session locally with `bootstrap_garmin.py`, upload to DynamoDB

### Issue: "TimeZone.validate() takes 2 positional arguments but 3 were given"
**Solution**: Use `withings-api==2.4.0` (not older versions)

### Issue: Withings webhook not triggering Lambda
**Cause**: Webhook URL not subscribed (the Withings developer portal callback URL is for OAuth, NOT webhooks)
**Solution**: Use `webhook_manager.py subscribe <lambda-url>`

## Monitoring

View Lambda logs:
```bash
aws logs tail '/aws/lambda/withings-garmin-sync-prod' --region ca-central-1 --follow
```

Test manual sync:
```bash
curl -X POST https://YOUR-API-GATEWAY-URL/prod/sync/manual
```

## Security
- Credentials stored in AWS Secrets Manager (not in code)
- Garmin session stored in DynamoDB (encrypted at rest)
- API Gateway provides HTTPS automatically
- Never commit `.env`, `secrets.json`, or session files
