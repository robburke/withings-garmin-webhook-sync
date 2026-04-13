# Fix Notes

## 2026-02-28: Garmin Sync Stopped Working (~Feb 9, 2026)

### Symptoms
- Weights stopped appearing in Garmin Connect
- Lambda logs showed 403 errors, then auth failures
- Service had been working fine for ~6 weeks

### Root Cause

`bootstrap_garmin.py` was uploading the Garmin session to the **wrong DynamoDB table**:

```
bootstrap_garmin.py wrote to:  withings-garmin-sync-tokens   (hardcoded, wrong)
Lambda reads from:              withings-garmin-tokens-prod   (from TOKEN_TABLE_NAME env var)
```

Because Lambda never found a valid DynamoDB session, it fell back to `garth.login()` (email + password) on **every cold start**. This worked for about 6 weeks until the Garmin OAuth2 refresh token expired (~Feb 9, 2026). After expiry, Garmin started requiring MFA for fresh logins, which Lambda cannot handle interactively.

### Fixes Applied

**`bootstrap_garmin.py`** — Fixed wrong table name:
```python
# Before (broken):
table_name = 'withings-garmin-sync-tokens'

# After (fixed):
table_name = os.environ.get('TOKEN_TABLE_NAME', 'withings-garmin-tokens-prod')
```

**`garmin_client.py`** — Added User-Agent after `garth.login()` (was only set after `garth.resume()`):
```python
garth.login(email, password)
garth.client.domain = "garmin.com"
garth.client.sess.headers['User-Agent'] = 'GCM-iOS-5.7.2.1'  # Added
```

**`garmin_client.py`** — Persist refreshed OAuth2 tokens back to DynamoDB after session verification:
```python
self.client.get_full_name()  # verify session
if self.is_lambda:
    garth.save(self.session_dir)       # write refreshed tokens to /tmp
    self._save_session_to_dynamodb()   # then persist to DynamoDB
```

### Recovery Steps

After deploying the code fixes, re-bootstrap the Garmin session:

```bash
python bootstrap_garmin.py
```

This re-authenticates interactively (handles MFA if prompted) and uploads a fresh session to the correct DynamoDB table. Then deploy:

```bash
sam build && sam deploy --no-confirm-changeset
```

Verify with a manual sync:
```bash
curl -X POST https://j7ebm5kb9l.execute-api.ca-central-1.amazonaws.com/prod/sync/manual
# Expected: {"status": "success", "synced": N, "skipped": N}
```

### If This Happens Again

The Garmin OAuth2 **refresh token expires every ~6 months**. When it does:

1. Run `python bootstrap_garmin.py` locally to get a fresh session
2. This uploads new tokens to `withings-garmin-tokens-prod` in DynamoDB
3. Lambda will pick them up on the next invocation — no redeploy needed

Watch for this pattern in CloudWatch logs:
```
Session exists but is invalid
Authenticating with Garmin Connect as ...
```
This means Lambda is falling back to password login and the session in DynamoDB is stale or missing.

---

## 2026-03-01: Withings Webhook Subscription Missing

### Symptoms
- Scale measurements not syncing automatically
- Manual sync works fine (`curl -X POST .../sync/manual`)
- No Lambda invocations in CloudWatch around the time of the measurement

### Root Cause

The Withings webhook subscription was gone — Withings had no callback URL to notify when a measurement was taken, so Lambda was never invoked. The subscription likely disappeared due to repeated delivery failures during the February outage.

### Diagnosis

```bash
python webhook_manager.py list
# Shows: "No active webhooks found."
```

### Fix

Re-subscribe the webhook:

```bash
python webhook_manager.py subscribe https://j7ebm5kb9l.execute-api.ca-central-1.amazonaws.com/prod/webhook/withings
```

Verify it stuck:

```bash
python webhook_manager.py list
# Should show the Lambda URL as an active subscription
```

### If This Happens Again

**First thing to check when sync stops:** run `python webhook_manager.py list`.

- If "No active webhooks found" → re-subscribe (see above)
- If subscription is listed → check CloudWatch logs and Garmin session (see Feb 2026 fix above)

Note: the local `.env` `WITHINGS_REFRESH_TOKEN` may be stale if Lambda has been auto-refreshing for a while. If `webhook_manager.py` fails with `invalid refresh_token`, pull the current token from Secrets Manager:

```bash
aws --region ca-central-1 secretsmanager get-secret-value \
  --secret-id withings-garmin-secrets-prod \
  --query SecretString --output text \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['WITHINGS_REFRESH_TOKEN'])"
```

Then update `WITHINGS_REFRESH_TOKEN` in `.env` with that value.
