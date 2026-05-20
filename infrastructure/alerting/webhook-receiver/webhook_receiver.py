#!/usr/bin/env python3
"""
Alertmanager Webhook Receiver - Ablage-System OCR
Custom webhook endpoint for processing Alertmanager alerts
"""

import os
import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List, Any

from flask import Flask, request, jsonify
import requests
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger(__name__)

app = Flask(__name__)

# Configuration
# S.8 SECURITY FIX: Kein hardcoded Default mehr - Secret MUSS gesetzt sein
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')
if not WEBHOOK_SECRET:
    raise ValueError(
        "WEBHOOK_SECRET environment variable is required. "
        "Set a strong secret (min 32 characters) for webhook authentication."
    )
BACKEND_API_URL = os.getenv('BACKEND_API_URL', 'http://backend:8000')


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook HMAC-SHA256 signature.

    S.8 SECURITY FIX: Verwendet HMAC-SHA256 statt einfachen String-Vergleich.
    hmac.compare_digest() ist timing-attack-resistant.

    Args:
        payload: Raw request body bytes
        signature: X-Webhook-Signature header value
        secret: Webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def verify_webhook_secret(secret: str) -> bool:
    """Verify webhook secret using constant-time comparison.

    S.8 SECURITY FIX: Verwendet hmac.compare_digest() statt ==
    um Timing-Attacken zu verhindern.

    Args:
        secret: Secret from X-Webhook-Secret header

    Returns:
        True if secret matches, False otherwise
    """
    return hmac.compare_digest(secret, WEBHOOK_SECRET)


def format_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Format alert for storage/processing."""
    return {
        'alert_name': alert.get('labels', {}).get('alertname', 'unknown'),
        'severity': alert.get('labels', {}).get('severity', 'unknown'),
        'service': alert.get('labels', {}).get('service', 'unknown'),
        'instance': alert.get('labels', {}).get('instance'),
        'status': alert.get('status', 'unknown'),
        'summary': alert.get('annotations', {}).get('summary', ''),
        'description': alert.get('annotations', {}).get('description', ''),
        'starts_at': alert.get('startsAt'),
        'ends_at': alert.get('endsAt'),
        'generator_url': alert.get('generatorURL'),
        'fingerprint': alert.get('fingerprint'),
        'labels': alert.get('labels', {}),
        'annotations': alert.get('annotations', {}),
        'received_at': datetime.utcnow().isoformat()
    }


def store_alert_in_database(alert_data: Dict[str, Any]) -> bool:
    """Store alert in backend database."""
    try:
        response = requests.post(
            f'{BACKEND_API_URL}/api/v1/alerts/',
            json=alert_data,
            timeout=5
        )
        response.raise_for_status()
        logger.info("alert_stored_in_database", alert_name=alert_data['alert_name'])
        return True
    except requests.RequestException as e:
        logger.error("failed_to_store_alert", error=str(e))
        return False


def trigger_custom_action(alert: Dict[str, Any]) -> None:
    """Trigger custom actions based on alert type."""
    alert_name = alert.get('labels', {}).get('alertname', '')
    severity = alert.get('labels', {}).get('severity', '')

    # Example: Auto-scale workers on high load
    if alert_name == 'HighDocumentQueueLength' and severity == 'high':
        logger.info("Triggering worker auto-scaling...")
        try:
            requests.post(
                f'{BACKEND_API_URL}/api/v1/workers/scale',
                json={'desired_count': 5},
                timeout=5
            )
        except requests.RequestException as e:
            logger.error("failed_to_trigger_auto_scaling", error=str(e))

    # Example: Clear GPU memory on OOM warning
    if 'GPU' in alert_name and 'Memory' in alert_name:
        logger.info("Triggering GPU memory cleanup...")
        try:
            requests.post(
                f'{BACKEND_API_URL}/api/v1/gpu/clear-cache',
                timeout=5
            )
        except requests.RequestException as e:
            logger.error("failed_to_trigger_gpu_cleanup", error=str(e))


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'webhook-receiver',
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Receive alerts from Alertmanager.

    Expected payload format:
    {
        "version": "4",
        "groupKey": "...",
        "status": "firing|resolved",
        "receiver": "webhook",
        "groupLabels": {...},
        "commonLabels": {...},
        "commonAnnotations": {...},
        "externalURL": "...",
        "alerts": [...]
    }
    """
    # Verify webhook secret
    secret = request.headers.get('X-Webhook-Secret', '')
    if not verify_webhook_secret(secret):
        logger.warning("invalid_webhook_secret", remote_addr=request.remote_addr)
        return jsonify({'error': 'Invalid webhook secret'}), 401

    # Parse payload
    try:
        payload = request.get_json()
    except Exception as e:
        logger.error("failed_to_parse_webhook_payload", error=str(e))
        return jsonify({'error': 'Invalid JSON payload'}), 400

    if not payload:
        return jsonify({'error': 'Empty payload'}), 400

    # Log webhook reception
    logger.info(
        "received_webhook_from_alertmanager",
        status=payload.get('status'),
        alert_count=len(payload.get('alerts', []))
    )

    # Process alerts
    alerts = payload.get('alerts', [])
    processed_count = 0
    failed_count = 0

    for alert in alerts:
        try:
            # Format alert
            alert_data = format_alert(alert)

            # Store in database
            if store_alert_in_database(alert_data):
                processed_count += 1
            else:
                failed_count += 1

            # Trigger custom actions
            if alert.get('status') == 'firing':
                trigger_custom_action(alert)

        except Exception as e:
            logger.exception("error_processing_alert", error=str(e))
            failed_count += 1

    # Return response
    return jsonify({
        'status': 'success',
        'processed': processed_count,
        'failed': failed_count,
        'total': len(alerts),
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/webhook/test', methods=['POST'])
def webhook_test():
    """Test endpoint for webhook testing."""
    payload = request.get_json()

    logger.info("received_test_webhook")
    logger.info("test_webhook_payload", payload=payload)

    return jsonify({
        'status': 'success',
        'message': 'Test webhook received',
        'payload': payload
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
