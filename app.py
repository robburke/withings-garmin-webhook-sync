"""
Withings to Garmin Webhook Sync
Main Flask application for receiving Withings webhooks and syncing to Garmin
"""
import os
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from sync_service import SyncService
from config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
config = Config()
sync_service = SyncService(config)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}), 200


@app.route('/webhook/withings', methods=['HEAD', 'GET', 'POST'])
def withings_webhook():
    """
    Withings webhook endpoint

    Withings sends:
    - HEAD request to verify endpoint exists
    - GET request during subscription setup
    - POST request when new measurement is available
    """

    if request.method == 'HEAD':
        logger.info("Received HEAD request from Withings (health check)")
        return '', 200

    if request.method == 'GET':
        logger.info("Received GET request from Withings (subscription verification)")
        return '', 200

    if request.method == 'POST':
        try:
            data = request.json
            logger.info(f"Received webhook from Withings: {data}")

            # Withings sends notifications like:
            # {"userid": "12345", "appli": 1, "startdate": 1234567890, "enddate": 1234567891}
            # appli: 1 = weight, 4 = sleep, etc.

            if data.get('appli') == 1:  # Weight measurement
                user_id = data.get('userid')
                start_date = data.get('startdate')
                end_date = data.get('enddate')

                logger.info(f"Processing weight measurement for user {user_id}")

                # Trigger sync
                result = sync_service.sync_weights(user_id, start_date, end_date)

                return jsonify({
                    'status': 'success',
                    'synced': result['synced'],
                    'skipped': result['skipped'],
                    'message': result['message']
                }), 200
            else:
                logger.info(f"Ignoring non-weight notification (appli={data.get('appli')})")
                return jsonify({'status': 'ignored', 'reason': 'not a weight measurement'}), 200

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    return jsonify({'status': 'error', 'message': 'Method not allowed'}), 405


@app.route('/sync/manual', methods=['POST'])
def manual_sync():
    """
    Manual sync endpoint for testing or one-off syncs
    Optional query params: days (default: 7)
    """
    try:
        days = int(request.args.get('days', 7))
        logger.info(f"Manual sync triggered for last {days} days")

        result = sync_service.sync_recent_weights(days=days)

        return jsonify({
            'status': 'success',
            'synced': result['synced'],
            'skipped': result['skipped'],
            'message': result['message']
        }), 200

    except Exception as e:
        logger.error(f"Error in manual sync: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Withings-Garmin Webhook Sync server on port {port}")
    logger.info(f"Webhook URL will be: http://localhost:{port}/webhook/withings")
    logger.info(f"Don't forget to expose this with ngrok!")

    app.run(host='0.0.0.0', port=port, debug=False)
