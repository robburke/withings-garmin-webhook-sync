"""
AWS Lambda Handler for Withings to Garmin Webhook Sync

This module adapts the Flask application logic to work with AWS Lambda + API Gateway.

Version: 2026-01-19 10:20 - Fixed pydantic/garth version compatibility
"""
import json
import logging
import os
from datetime import datetime
from urllib.parse import parse_qs

# Configure logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Lazy-load heavy imports to improve cold start
_sync_service = None
_config = None


def get_config():
    """Lazy-load configuration"""
    global _config
    if _config is None:
        from config import Config
        _config = Config()
    return _config


def get_sync_service():
    """Lazy-load sync service (includes Withings/Garmin clients)"""
    global _sync_service
    if _sync_service is None:
        from sync_service import SyncService
        _sync_service = SyncService(get_config())
    return _sync_service


def create_response(status_code: int, body: dict) -> dict:
    """Create a properly formatted API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }


def parse_form_body(body: str, is_base64: bool = False) -> dict:
    """
    Parse form-encoded body from API Gateway event.
    Withings sends webhook data as application/x-www-form-urlencoded
    """
    if not body:
        return {}

    if is_base64:
        import base64
        body = base64.b64decode(body).decode('utf-8')

    parsed = parse_qs(body)
    # parse_qs returns lists, we want single values
    result = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    # Convert known integer fields
    for field in ['appli', 'startdate', 'enddate']:
        if field in result:
            try:
                result[field] = int(result[field])
            except (ValueError, TypeError):
                pass

    return result


def handle_health(event: dict, context) -> dict:
    """Handle GET /health"""
    return create_response(200, {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'environment': os.environ.get('ENVIRONMENT', 'unknown')
    })


def handle_webhook_head(event: dict, context) -> dict:
    """Handle HEAD /webhook/withings - Withings health check"""
    logger.info("Received HEAD request from Withings (health check)")
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/plain'},
        'body': ''
    }


def handle_webhook_get(event: dict, context) -> dict:
    """Handle GET /webhook/withings - Withings subscription verification"""
    logger.info("Received GET request from Withings (subscription verification)")
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/plain'},
        'body': ''
    }


def handle_webhook_post(event: dict, context) -> dict:
    """Handle POST /webhook/withings - Process Withings measurement notification"""
    try:
        # Parse the form-encoded body
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)

        # Try form data first (Withings sends form-encoded)
        content_type = event.get('headers', {}).get('content-type', '') or \
                       event.get('headers', {}).get('Content-Type', '')

        if 'application/x-www-form-urlencoded' in content_type:
            data = parse_form_body(body, is_base64)
        else:
            # Fall back to JSON
            if is_base64:
                import base64
                body = base64.b64decode(body).decode('utf-8')
            data = json.loads(body) if body else {}

        logger.info(f"Received webhook from Withings: {data}")

        # Check if this is a weight measurement (appli=1)
        if data.get('appli') == 1:
            user_id = data.get('userid')
            start_date = data.get('startdate')
            end_date = data.get('enddate')

            logger.info(f"Processing weight measurement for user {user_id}")

            # Get sync service and process
            sync_service = get_sync_service()
            result = sync_service.sync_weights(user_id, start_date, end_date)

            return create_response(200, {
                'status': 'success',
                'synced': result['synced'],
                'skipped': result['skipped'],
                'message': result['message']
            })
        else:
            logger.info(f"Ignoring non-weight notification (appli={data.get('appli')})")
            return create_response(200, {
                'status': 'ignored',
                'reason': 'not a weight measurement'
            })

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return create_response(500, {
            'status': 'error',
            'message': str(e)
        })


def handle_manual_sync(event: dict, context) -> dict:
    """Handle POST /sync/manual - Manual sync trigger"""
    try:
        # Get days parameter from query string
        query_params = event.get('queryStringParameters') or {}
        days = int(query_params.get('days', 7))

        logger.info(f"Manual sync triggered for last {days} days")

        sync_service = get_sync_service()
        result = sync_service.sync_recent_weights(days=days)

        return create_response(200, {
            'status': 'success',
            'synced': result['synced'],
            'skipped': result['skipped'],
            'message': result['message']
        })

    except Exception as e:
        logger.error(f"Error in manual sync: {str(e)}", exc_info=True)
        return create_response(500, {
            'status': 'error',
            'message': str(e)
        })


def handler(event: dict, context) -> dict:
    """
    Main Lambda handler - routes requests to appropriate handlers.

    This is the entry point that AWS Lambda calls.
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # Extract HTTP method and path
    http_method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method', ''))
    path = event.get('path', event.get('rawPath', ''))

    # Route to appropriate handler
    if '/health' in path:
        return handle_health(event, context)

    elif '/webhook/withings' in path:
        if http_method == 'HEAD':
            return handle_webhook_head(event, context)
        elif http_method == 'GET':
            return handle_webhook_get(event, context)
        elif http_method == 'POST':
            return handle_webhook_post(event, context)

    elif '/sync/manual' in path:
        if http_method == 'POST':
            return handle_manual_sync(event, context)

    # Unknown route
    return create_response(404, {
        'status': 'error',
        'message': f'Unknown route: {http_method} {path}'
    })
