# Withings to Garmin Webhook Sync

Automatically sync weight measurements from your Withings smart scale to Garmin Connect in real-time using webhooks. Built for people who want instant synchronization the moment they step off their scale.

## 🚀 Features

- **Instant Real-time Sync**: Uses Withings webhooks to sync weight measurements immediately when you step on your scale
- **Smart Duplicate Prevention**: Prevents duplicate entries using configurable timestamp (±2 min) and weight (±0.1 kg) tolerances
- **Safety Limits**: Maximum 5 entries per sync to prevent accidental mass uploads
- **Manual Sync**: Trigger manual syncs for historical data (last N days)
- **Comprehensive Logging**: All operations logged to both file and console
- **Automatic Token Refresh**: Withings OAuth tokens automatically refreshed as needed
- **Health Check Endpoint**: Monitor server status

## 📋 Prerequisites

- **Withings Account**: With at least one smart scale/body composition device
- **Garmin Connect Account**: Free account at https://connect.garmin.com
- **Python 3.8+**: With pip package manager
- **Withings Developer App**: Create at https://developer.withings.com
- **ngrok Account**: Free account at https://ngrok.com (required for webhook HTTPS endpoint)
- **Local Machine**: PC/Mac that you can keep running for real-time sync

## 🔧 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/robburke/withings-garmin-webhook-sync.git
cd withings-garmin-webhook-sync
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create Withings Developer Application

1. Go to https://developer.withings.com/dashboard
2. Click "Create an app"
3. Fill in the details:
   - **Application Name**: `Garmin Sync` (or your preferred name)
   - **Description**: Personal weight sync application
   - **Callback URI**: `http://localhost:5000/callback`
   - **Application Website**: Can use your GitHub repo URL
4. Note your **Client ID** and **Client Secret**

### 4. Configure Environment Variables

```bash
# Copy the example configuration
cp .env.example .env

# Edit .env with your credentials
# - Add your Withings Client ID and Client Secret
# - Add your Garmin Connect email and password
```

Your `.env` file should look like:

```bash
WITHINGS_CLIENT_ID=your_client_id_here
WITHINGS_CLIENT_SECRET=your_client_secret_here
WITHINGS_CALLBACK_URI=http://localhost:5000/callback
WITHINGS_REFRESH_TOKEN=

GARMIN_EMAIL=your_garmin_email@example.com
GARMIN_PASSWORD=your_garmin_password

PORT=5000
LOG_LEVEL=INFO
```

### 5. Complete Withings OAuth Authentication

Run the interactive setup script to authorize the application:

```bash
python setup.py
```

This will:
1. Open your browser to the Withings authorization page
2. Ask you to approve access to your weight data
3. Save the refresh token to your `.env` file automatically

### 6. Install and Configure ngrok

Withings webhooks require an HTTPS endpoint. ngrok provides a secure tunnel to your local server.

1. Sign up at https://ngrok.com
2. Download and install ngrok
3. Authenticate ngrok with your token:
   ```bash
   ngrok config add-authtoken YOUR_NGROK_TOKEN
   ```

4. Start ngrok tunnel (in a separate terminal):
   ```bash
   ngrok http 5000
   ```

5. Note your ngrok HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 7. Start the Flask Server

In your main terminal:

```bash
python app.py
```

You should see:
```
Starting Withings-Garmin Webhook Sync server on port 5000
Webhook URL will be: http://localhost:5000/webhook/withings
Don't forget to expose this with ngrok!
```

### 8. Subscribe to Withings Webhooks

Use the webhook manager to subscribe to weight measurement notifications:

```bash
python webhook_manager.py subscribe https://your-ngrok-url.ngrok.io/webhook/withings
```

Replace `your-ngrok-url` with your actual ngrok URL from step 6.

To verify subscription:
```bash
python webhook_manager.py list
```

## 🎯 Usage

### Automatic Sync (Real-time)

Once everything is set up:

1. Keep the Flask server running (`python app.py`)
2. Keep ngrok running (`ngrok http 5000`)
3. Step on your Withings scale
4. Weight automatically appears in Garmin Connect within seconds!

Check the console or `sync.log` file to see the sync activity.

### Manual Sync

To sync historical data from the last 7 days:

```bash
curl -X POST http://localhost:5000/sync/manual
```

To sync a custom number of days (e.g., last 30 days):

```bash
curl -X POST http://localhost:5000/sync/manual?days=30
```

### Health Check

Verify the server is running:

```bash
curl http://localhost:5000/health
```

## ⚙️ Configuration

### Deduplication Settings

Edit `deduplicator.py` to adjust duplicate detection:

```python
DEFAULT_TIME_TOLERANCE = 120  # seconds (±2 minutes)
DEFAULT_WEIGHT_TOLERANCE = 0.1  # kg (±100g)
```

### Safety Limits

Edit `sync_service.py` to change the maximum entries per sync:

```python
MAX_ENTRIES_PER_SYNC = 5  # Maximum weight entries to sync at once
```

### Duplicate Detection Window

Edit `sync_service.py` to change how far back to check for duplicates:

```python
lookback_days = 30  # Check last 30 days of Garmin data
```

## 📁 Project Structure

```
withings-garmin-webhook-sync/
├── app.py                  # Main Flask application with webhook endpoints
├── sync_service.py         # Core sync logic orchestrating Withings → Garmin
├── withings_client.py      # Withings API wrapper (OAuth, measurements, webhooks)
├── garmin_client.py        # Garmin Connect API wrapper (auth, fetch, upload)
├── deduplicator.py         # Duplicate detection logic with tolerances
├── config.py               # Configuration management from .env
├── setup.py                # Interactive OAuth setup script
├── webhook_manager.py      # CLI utility for webhook management
├── requirements.txt        # Python dependencies
├── .env.example            # Template for environment variables
├── .gitignore              # Git ignore rules (includes .env)
└── sync.log                # Application log file (created on first run)
```

## 🔍 Troubleshooting

### Webhook Not Receiving Data

1. **Check ngrok is running**: Verify the HTTPS URL is active
2. **Verify subscription**: Run `python webhook_manager.py list`
3. **Check Flask logs**: Look at console output or `sync.log`
4. **Test webhook endpoint**:
   ```bash
   curl https://your-ngrok-url.ngrok.io/webhook/withings
   ```

### Authentication Issues

**Withings "Invalid Token"**:
- Run `python setup.py` again to refresh OAuth tokens
- Check that `WITHINGS_REFRESH_TOKEN` is set in `.env`

**Garmin Login Failed**:
- Verify email/password in `.env` are correct
- Check if Garmin Connect requires 2FA (not currently supported)
- Try logging into Garmin Connect website manually first

### Duplicates Still Appearing

- Increase time/weight tolerances in `deduplicator.py`
- Check if Garmin entries are in different units (kg vs lbs)
- Review logs to see what's being detected as duplicates

### ngrok URL Changes

Free ngrok URLs change each time you restart ngrok. When this happens:

1. Note your new ngrok URL
2. Unsubscribe old webhook:
   ```bash
   python webhook_manager.py unsubscribe
   ```
3. Subscribe with new URL:
   ```bash
   python webhook_manager.py subscribe https://new-ngrok-url.ngrok.io/webhook/withings
   ```

**Pro Tip**: ngrok paid plans offer permanent URLs

## 🔒 Security Notes

- **Credentials Storage**: All credentials stored in `.env` (gitignored, never committed)
- **Garmin Password**: Stored in plaintext locally (limitation of unofficial API)
- **HTTPS Required**: Withings webhooks require HTTPS (provided by ngrok)
- **Token Refresh**: Withings tokens automatically refreshed and updated
- **Local Only**: This runs on your local machine, no cloud services involved

## 🛠️ Development

### Running Tests

```bash
# Test manual sync
curl -X POST http://localhost:5000/sync/manual?days=1

# Check health endpoint
curl http://localhost:5000/health

# View logs
tail -f sync.log
```

### Unsubscribing from Webhooks

To stop receiving webhook notifications:

```bash
python webhook_manager.py unsubscribe
```

## 📝 How It Works

1. **User Steps on Scale**: Withings scale measures weight
2. **Webhook Notification**: Withings sends POST to your webhook endpoint
3. **Fetch Measurement**: App retrieves measurement data from Withings API
4. **Duplicate Check**: Compares against last 30 days of Garmin weights
5. **Filter & Upload**: New measurements (max 5) uploaded to Garmin Connect
6. **Instant Sync**: Weight appears in Garmin Connect immediately

## 🤝 Credits

- **Withings API**: Official Python library by Withings
- **Garmin Connect**: Community-maintained `garminconnect` library
- **ngrok**: Secure tunneling service for local webhooks

## ⚠️ Disclaimer

This application uses an unofficial Garmin Connect library. While it works reliably, it's not endorsed by Garmin. Use at your own risk.

The official Withings → Garmin sync exists but may have delays. This project is for users who want instant synchronization.

## 📧 Support

Created by Rob Burke (rob@robburke.net)

For issues or questions, please open an issue on GitHub.

## 📄 License

MIT License - feel free to use and modify for personal use.

---

**Built for impatient people who want their weight data synced instantly!** ⚡
