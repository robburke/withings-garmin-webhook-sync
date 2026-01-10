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
            # Withings sends data as form-encoded, not JSON
            # Try to get data from form first, fall back to JSON
            if request.form:
                data = request.form.to_dict()
                # Convert string values to integers where needed
                if 'appli' in data:
                    data['appli'] = int(data['appli'])
                if 'startdate' in data:
                    data['startdate'] = int(data['startdate'])
                if 'enddate' in data:
                    data['enddate'] = int(data['enddate'])
            else:
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


@app.route('/test/garmin-weights', methods=['GET'])
def test_garmin_weights():
    """
    Test endpoint to verify we can actually read weights from Garmin
    Usage: GET /test/garmin-weights?days=30
    """
    try:
        from datetime import datetime, timedelta

        days = int(request.args.get('days', 30))
        logger.info(f"=== TESTING GARMIN WEIGHT FETCH FOR LAST {days} DAYS ===")

        # Test fetching weights from Garmin
        since = datetime.now() - timedelta(days=days)
        until = datetime.now()

        logger.info(f"Date range: {since.date()} to {until.date()}")
        weights = sync_service.garmin.get_weights(since=since, until=until)

        logger.info(f"=== RESULT: Found {len(weights)} weights ===")
        for w in weights:
            logger.info(f"  Weight: {w['weight']}kg at {w['timestamp']}")

        return jsonify({
            'status': 'success',
            'date_range': {
                'from': since.isoformat(),
                'to': until.isoformat(),
                'days': days
            },
            'weights_found': len(weights),
            'weights': [{'weight': w['weight'], 'timestamp': str(w['timestamp'])} for w in weights]
        }), 200

    except Exception as e:
        logger.error(f"Error testing Garmin weights: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Withings-Garmin Webhook Sync server on port {port}")
    logger.info(f"Webhook URL will be: http://localhost:{port}/webhook/withings")
    logger.info(f"Don't forget to expose this with ngrok!")

    app.run(host='0.0.0.0', port=port, debug=False)
