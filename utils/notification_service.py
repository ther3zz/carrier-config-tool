import asyncio
import httpx
import hmac
import hashlib
import json
import threading
from datetime import datetime, timezone

from . import settings_manager
from . import logger

async def send_notification(event_type: str, data: dict):
    """
    Constructs and sends a webhook notification based on global settings.
    Checks both the master switch and event-specific switches before sending.
    Supports both JSON and flattened form-urlencoded content types.
    """
    notification_logger = logger.get_notification_logger()

    if not settings_manager.get_setting('notifications_enabled'):
        return

    event_setting_map = {
        "subaccount.created": "notifications_on_subaccount_created",
        "did.provisioned": "notifications_on_did_provisioned",
        "did.released": "notifications_on_did_released",
        "test.event": "notifications_enabled",
        # Map batch events to their corresponding single-event setting
        "did.provisioned.batch": "notifications_on_did_provisioned",
        "did.released.batch": "notifications_on_did_released",
        "did.updated.batch": "notifications_on_did_provisioned" # Re-use provisioning setting for updates
    }
    
    event_key = event_setting_map.get(event_type)
    
    if not event_key or not settings_manager.get_setting(event_key):
        print(f"Notification Service: Skipping event '{event_type}' as it is disabled in settings.")
        return

    webhook_url = settings_manager.get_setting('notifications_webhook_url')
    if not webhook_url:
        print(f"Notification Service: Aborting send for '{event_type}'. Webhook URL is not configured.")
        return

    secret = settings_manager.get_setting('notifications_secret')
    content_type = settings_manager.get_setting('notifications_content_type', 'application/json')

    payload = {
        'event_type': event_type,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': data
    }
    
    headers = {}
    request_kwargs = {'timeout': 10.0}
    payload_for_signing = None
    final_payload_sent = {}

    if content_type == 'application/x-www-form-urlencoded':
        flat_form_data = {
            'event_type': payload['event_type'],
            'timestamp': payload['timestamp'],
            **payload['data']
        }
        request_kwargs['data'] = flat_form_data
        final_payload_sent = flat_form_data
        
        if secret:
            payload_for_signing = json.dumps(payload).encode('utf-8')
    else: # Default to application/json
        json_payload_bytes = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        request_kwargs['content'] = json_payload_bytes
        final_payload_sent = payload
        if secret:
            payload_for_signing = json_payload_bytes

    if secret and payload_for_signing:
        signature_hash = hmac.new(secret.encode('utf-8'), payload_for_signing, hashlib.sha256)
        signature = signature_hash.hexdigest()
        headers['X-Webhook-Signature-256'] = f"sha256={signature}"
    
    request_kwargs['headers'] = headers

    log_entry = {
        "event_type": event_type,
        "webhook_url": webhook_url,
        "request": {
            "headers": headers,
            "payload": final_payload_sent
        },
        "response": {}
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, **request_kwargs)
            
            log_entry["response"] = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text
            }
            
            response.raise_for_status() 
            notification_logger.info(json.dumps(log_entry))
            print(f"Notification Sent: Event '{event_type}' to {webhook_url} as {content_type}. Status: {response.status_code}")

    
    except httpx.HTTPStatusError as e:
        # This catches 4xx and 5xx response errors specifically
        error_details = {
            "error": "HTTPStatusError",
            "status_code": e.response.status_code,
            "response_body": e.response.text
        }
        log_entry["response"].update(error_details)
        notification_logger.error(json.dumps(log_entry))
        print(f"Notification HTTP Error: Event '{event_type}' to {webhook_url} failed with status {e.response.status_code}. Response Body: {e.response.text}")
    
    except httpx.RequestError as e:
        log_entry["response"] = {"error": f"RequestError: {str(e)}"}
        notification_logger.error(json.dumps(log_entry))
        print(f"Notification Request Error: Failed to send event '{event_type}' to {webhook_url}. Details: {e}")
    except Exception as e:
        log_entry["response"] = {"error": f"UnexpectedError: {str(e)}"}
        notification_logger.error(json.dumps(log_entry))
        print(f"Notification Unexpected Error: An unexpected error occurred while sending event '{event_type}'. Details: {e}")


def _run_async_in_thread(coro):
    """Helper function to run an async coroutine in a new event loop."""
    asyncio.run(coro)

def fire_and_forget(event_type: str, data: dict):
    """
    Synchronous wrapper that starts the async notification in a separate background thread.
    """
    coroutine = send_notification(event_type, data)
    thread = threading.Thread(target=_run_async_in_thread, args=(coroutine,))
    thread.daemon = True
    thread.start()
