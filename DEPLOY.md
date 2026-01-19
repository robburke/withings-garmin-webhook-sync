# Deploying Withings-Garmin Sync to AWS Lambda

This guide covers deploying the serverless version to AWS.

## Prerequisites

1. **AWS CLI** installed and configured with your credentials
   ```bash
   aws configure
   ```

2. **AWS SAM CLI** installed
   - Windows: `choco install aws-sam-cli` or download from [AWS](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
   - Mac: `brew install aws-sam-cli`

3. **Docker** installed (required for SAM to build Python dependencies)

4. **Your existing credentials** from the local setup:
   - Withings Client ID and Secret (from Withings Developer Portal)
   - Withings Refresh Token (from your working local `.env`)
   - Garmin email and password

## Deployment Steps

### Step 1: Build the Application

```bash
cd withings-garmin-webhook-sync
sam build
```

This packages your code and dependencies for Lambda.

### Step 2: Deploy to AWS

```bash
sam deploy --guided
```

On first run, this will ask you:
- **Stack Name**: `withings-garmin-sync` (or your choice)
- **AWS Region**: Choose your preferred region (e.g., `us-east-1`)
- **Environment**: `prod` (or `dev` for testing)
- **Confirm changes**: Yes
- **Allow IAM role creation**: Yes
- **Save arguments to config file**: Yes

### Step 3: Configure Secrets

After deployment, you need to add your actual credentials to AWS Secrets Manager.

1. Find your secret ARN in the deployment outputs, or:
   ```bash
   aws secretsmanager list-secrets --query "SecretList[?Name=='withings-garmin-secrets-prod'].ARN"
   ```

2. Update the secret with your real credentials:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id withings-garmin-secrets-prod \
     --secret-string '{
       "WITHINGS_CLIENT_ID": "your_client_id",
       "WITHINGS_CLIENT_SECRET": "your_client_secret",
       "WITHINGS_REFRESH_TOKEN": "your_refresh_token_from_local_env",
       "GARMIN_EMAIL": "your_garmin_email",
       "GARMIN_PASSWORD": "your_garmin_password"
     }'
   ```

   **Important**: Copy your `WITHINGS_REFRESH_TOKEN` from your working local `.env` file.

### Step 4: Get Your Webhook URL

After deployment, SAM outputs your webhook URL:

```
WebhookUrl: https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/prod/webhook/withings
```

### Step 5: Update Withings Webhook Subscription

Update your Withings webhook to point to the new Lambda URL:

```bash
# Using the local webhook manager (with your local .env still configured)
python webhook_manager.py unsubscribe  # Remove old ngrok webhook
python webhook_manager.py subscribe --url https://YOUR_API_GATEWAY_URL/webhook/withings
```

Or via the Withings Developer Portal.

### Step 6: Test the Deployment

1. **Health check**:
   ```bash
   curl https://YOUR_API_GATEWAY_URL/health
   ```

2. **Manual sync** (optional):
   ```bash
   curl -X POST https://YOUR_API_GATEWAY_URL/sync/manual
   ```

3. **Step on your scale** - the webhook should trigger automatically!

## Monitoring

### View Lambda Logs

```bash
sam logs -n WebhookFunction --stack-name withings-garmin-sync --tail
```

Or in the AWS Console: CloudWatch > Log Groups > `/aws/lambda/withings-garmin-sync-prod`

### Check Function Invocations

AWS Console: Lambda > Functions > withings-garmin-sync-prod > Monitor

## Updating the Deployment

After making code changes:

```bash
sam build && sam deploy
```

## Costs

This setup uses pay-per-request pricing:
- **Lambda**: ~$0.20 per 1 million requests (you'll use maybe 30/month)
- **API Gateway**: ~$3.50 per 1 million requests
- **DynamoDB**: ~$0 (pay-per-request, minimal usage)
- **Secrets Manager**: ~$0.40/month per secret

**Estimated monthly cost**: < $1 for typical personal use

## Troubleshooting

### "Garmin login failed"

The Garmin session may have expired. Check CloudWatch logs for details. You may need to:
1. Delete the stored session from DynamoDB
2. Trigger a manual sync to force re-authentication

```bash
aws dynamodb delete-item \
  --table-name withings-garmin-tokens-prod \
  --key '{"token_type": {"S": "garmin_session"}}'
```

### "Withings auth failed"

The refresh token may have expired. Get a new one locally and update Secrets Manager:
1. Run the local app with `python reauth_withings.py`
2. Copy the new refresh token from `.env`
3. Update Secrets Manager (Step 3 above)

### Webhook not triggering

1. Verify the webhook URL in Withings Developer Portal
2. Check that API Gateway shows incoming requests
3. Check CloudWatch logs for the Lambda function

## Keeping Local Development Working

The local Flask app still works! The code auto-detects whether it's running in Lambda or locally:
- **Local**: Uses `.env` file and `.garmin_session/` directory
- **Lambda**: Uses Secrets Manager and DynamoDB

To run locally:
```bash
python app.py
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Withings API   │────▶│   API Gateway   │────▶│     Lambda      │
│  (webhook POST) │     │   (HTTPS URL)   │     │  (your code)    │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────────────┐
                        │                                │                                │
                        ▼                                ▼                                ▼
               ┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
               │ Secrets Manager │              │    DynamoDB     │              │  Garmin Connect │
               │  (credentials)  │              │ (Garmin tokens) │              │    (upload)     │
               └─────────────────┘              └─────────────────┘              └─────────────────┘
```
