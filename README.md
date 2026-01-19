# Withings to Garmin Webhook Sync

Automatically sync weight measurements from your Withings smart scale to Garmin Connect in real-time using webhooks. Runs entirely in the cloud on AWS Lambda - no local server required.

## Features

- **Instant Real-time Sync**: Uses Withings webhooks to sync weight measurements immediately when you step on your scale
- **Fully Serverless**: Runs on AWS Lambda - no local machine needed, works 24/7
- **Smart Duplicate Prevention**: Prevents duplicate entries using configurable timestamp (±2 min) and weight (±0.1 kg) tolerances
- **Safety Limits**: Maximum 5 entries per sync to prevent accidental mass uploads
- **Manual Sync**: Trigger manual syncs for historical data via API endpoint
- **Automatic Token Refresh**: OAuth tokens automatically refreshed as needed
- **Secure Credential Storage**: Uses AWS Secrets Manager and DynamoDB

## Architecture

```
┌─────────────┐      Webhook       ┌─────────────┐      Upload       ┌─────────────┐
│   Withings  │ ─────────────────> │ AWS Lambda  │ ─────────────────> │   Garmin    │
│    Scale    │                    │ + API GW    │                    │   Connect   │
└─────────────┘                    └─────────────┘                    └─────────────┘
                                          │
                                          ├── DynamoDB (Garmin session)
                                          └── Secrets Manager (credentials)
```

## Prerequisites

- **AWS Account**: With permissions to create Lambda, API Gateway, DynamoDB, Secrets Manager
- **AWS CLI**: Configured with your credentials (`aws configure`)
- **AWS SAM CLI**: Install from https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
- **Python 3.12**: For local bootstrap scripts
- **Withings Account**: With at least one smart scale
- **Withings Developer App**: Create at https://developer.withings.com
- **Garmin Connect Account**: Free account at https://connect.garmin.com

## Quick Start

### 1. Clone and Deploy

```bash
git clone https://github.com/robburke/withings-garmin-webhook-sync.git
cd withings-garmin-webhook-sync

# Build and deploy to AWS
sam build
sam deploy --guided
```

During guided deployment:
- Stack Name: `withings-garmin-sync`
- Region: Choose your preferred AWS region
- Accept defaults for other options

Note your API Gateway URL from the outputs (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com/prod`)

### 2. Configure Credentials

Create a `secrets.json` file (DO NOT commit this):

```json
{
  "WITHINGS_CLIENT_ID": "your_withings_client_id",
  "WITHINGS_CLIENT_SECRET": "your_withings_client_secret",
  "WITHINGS_REFRESH_TOKEN": "your_withings_refresh_token",
  "GARMIN_EMAIL": "your_garmin_email@example.com",
  "GARMIN_PASSWORD": "your_garmin_password"
}
```

Upload to AWS Secrets Manager:

```bash
aws secretsmanager put-secret-value \
  --secret-id withings-garmin-secrets-prod \
  --secret-string file://secrets.json \
  --region YOUR_REGION
```

### 3. Bootstrap Garmin Session

Garmin requires MFA authentication which can't be done in Lambda. Run the bootstrap script locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with your Garmin credentials
cp .env.example .env
# Edit .env with GARMIN_EMAIL and GARMIN_PASSWORD

# Bootstrap session (will open browser for MFA if needed)
python bootstrap_garmin.py
```

This authenticates with Garmin and uploads the session to DynamoDB.

### 4. Get Withings Refresh Token

If you don't have a Withings refresh token yet:

```bash
python reauth_withings.py
```

This opens a browser for Withings OAuth and saves the refresh token to `.env`. Then update Secrets Manager with the new token.

### 5. Subscribe Withings Webhook

```bash
python webhook_manager.py subscribe https://YOUR-API-GATEWAY-URL/prod/webhook/withings
```

### 6. Done! Test It

Step on your scale, or trigger a manual sync:

```bash
curl -X POST https://YOUR-API-GATEWAY-URL/prod/sync/manual
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/webhook/withings` | POST | Receives Withings notifications |
| `/webhook/withings` | HEAD/GET | Withings subscription verification |
| `/sync/manual` | POST | Manual sync for last 7 days |

## Monitoring

View Lambda logs:

```bash
aws logs tail '/aws/lambda/withings-garmin-sync-prod' --region YOUR_REGION --follow
```

## Configuration

### Deduplication Settings

Edit `deduplicator.py`:

```python
DEFAULT_TIME_TOLERANCE = 120  # seconds (±2 minutes)
DEFAULT_WEIGHT_TOLERANCE = 0.1  # kg (±100g)
```

### Safety Limits

Edit `sync_service.py`:

```python
MAX_ENTRIES_PER_SYNC = 5  # Maximum weight entries to sync at once
```

## Important: Dependency Constraints

There is a pydantic version conflict between libraries. The requirements are pinned to specific versions that work together:

```
withings-api==2.4.0
garminconnect==0.2.19
garth>=0.4.46,<0.5.0
pydantic>=1.10.12,<2.0.0
```

**DO NOT upgrade garth to 0.5.x** - it requires pydantic v2 which is incompatible with withings-api.

## Troubleshooting

### Weights Not Appearing in Garmin

The most common cause is the User-Agent issue. Garmin changed their API in November 2024 to reject old user agents. The code includes a fix for this, but if you're still having issues:

1. Check Lambda logs for empty `[]` responses from Garmin
2. Ensure `garmin_client.py` has the User-Agent fix: `garth.client.sess.headers['User-Agent'] = 'GCM-iOS-5.7.2.1'`

### Garmin MFA Issues

Lambda can't handle interactive MFA. You must bootstrap the session locally:

```bash
python bootstrap_garmin.py
```

### Withings Webhook Not Triggering

The Withings developer portal "callback URL" is for OAuth, NOT webhooks. You must subscribe to webhooks separately:

```bash
python webhook_manager.py subscribe https://YOUR-URL/prod/webhook/withings
python webhook_manager.py list  # Verify subscription
```

### pydantic ImportError

If you see `cannot import name 'ValidationInfo' from 'pydantic'`, you've upgraded garth too high. Pin it:

```
garth>=0.4.46,<0.5.0
```

## Project Structure

```
withings-garmin-webhook-sync/
├── template.yaml           # AWS SAM infrastructure definition
├── lambda_handler.py       # Lambda entry point
├── sync_service.py         # Core sync logic
├── withings_client.py      # Withings API wrapper
├── garmin_client.py        # Garmin API wrapper (includes User-Agent fix)
├── token_storage.py        # DynamoDB token persistence
├── config.py               # Configuration (auto-detects Lambda vs local)
├── deduplicator.py         # Duplicate detection logic
├── fit_encoder.py          # FIT file format encoder
├── bootstrap_garmin.py     # Local script to bootstrap Garmin session
├── webhook_manager.py      # CLI for webhook management
├── reauth_withings.py      # Interactive Withings OAuth setup
├── requirements.txt        # Python dependencies
├── requirements-lambda.txt # Lambda-specific dependencies
└── .claude/claude.md       # Development notes and learnings
```

## Local Development (Optional)

If you want to run locally instead of Lambda:

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Edit with your credentials

# Start Flask server
python app.py

# In another terminal, start ngrok
ngrok http 5000

# Subscribe webhook to ngrok URL
python webhook_manager.py subscribe https://YOUR-NGROK-URL/webhook/withings
```

## Security

- Credentials stored in AWS Secrets Manager (encrypted)
- Garmin session stored in DynamoDB (encrypted at rest)
- API Gateway provides HTTPS automatically
- Never commit `.env`, `secrets.json`, or session files

## Costs

AWS Lambda free tier includes 1M requests/month and 400,000 GB-seconds of compute. This application uses minimal resources - expect costs under $1/month for typical personal use.

## Credits

- **withings-api**: Official Python library by Withings
- **garminconnect**: Community-maintained Garmin Connect library
- **garth**: Garmin authentication library

## Disclaimer

This application uses an unofficial Garmin Connect library. While it works reliably, it's not endorsed by Garmin. Use at your own risk.

## License

MIT License - feel free to use and modify for personal use.

---

**Built for impatient people who want their weight data synced instantly - without running anything locally!**
