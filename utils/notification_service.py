# --- START OF FILE utils/notification_service.py ---

import asyncio
import httpx
import hmac
import hashlib
import json
import threading
from datetime import datetime, timezone

from . import settings_manager

# --- START: MODIFICATION ---
# REMOVED: The global async_client is removed to prevent it from being tied to a closed event loop.
# async_client = httpx.AsyncClient()
# --- END: MODIFICATION ---

async def send_notification(event_type: str, data: dict):
    """
    Constructs and sends a webhook notification based on global settings.
    Checks both the master switch and event-specific switches before sending.
    Supports both JSON and flattened form-urlencoded content types.
    """
    if not settings_manager.get_setting('notifications_enabled'):
        return

    event_setting_map = {
        "subaccount.created": "notifications_on_subaccount_created",
        "did.provisioned": "notifications_on_did_provisioned",
        "did.released": "notifications_on_did_released",
        "test.event": "notifications_enabled"
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

    # Construct the original, canonical payload structure
    payload = {
        'event_type': event_type,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': data
    }
    
    headers = {}
    request_kwargs = {'timeout': 10.0}
    payload_for_signing = None

    if content_type == 'application/x-www-form-urlencoded':
        # Create a new, flat dictionary by merging the top-level fields
        # with the fields from the nested 'data' dictionary.
        flat_form_data = {
            'event_type': payload['event_type'],
            'timestamp': payload['timestamp'],
            **payload['data']  # Unpack the 'data' dictionary here
        }
        request_kwargs['data'] = flat_form_data
        
        # For signature consistency, we always sign the canonical JSON representation
        if secret:
            payload_for_signing = json.dumps(payload).encode('utf-8')
    else:  # Default to application/json
        json_payload_bytes = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        request_kwargs['content'] = json_payload_bytes
        if secret:
            payload_for_signing = json_payload_bytes

    if secret and payload_for_signing:
        signature_hash = hmac.new(secret.encode('utf-8'), payload_for_signing, hashlib.sha256)
        signature = signature_hash.hexdigest()
        headers['X-Webhook-Signature-256'] = f"sha256={signature}"
    
    request_kwargs['headers'] = headers

    # --- START: MODIFICATION ---
    # Create the client within an 'async with' block. This ensures the client
    # is created and closed within the same event loop managed by 'asyncio.run()'.
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, **request_kwargs)
            response.raise_for_status() 
            print(f"Notification Sent: Event '{event_type}' to {webhook_url} as {content_type}. Status: {response.status_code}")
    # --- END: MODIFICATION ---
    except httpx.RequestError as e:
        print(f"Notification Error: Failed to send event '{event_type}' to {webhook_url}. Details: {e}")
    except Exception as e:
        print(f"Notification Error: An unexpected error occurred while sending webhook. Details: {e}")


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

# --- END OF FILE utils/notification_service.py ---