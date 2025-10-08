# --- START OF FILE utils/notification_service.py ---

import asyncio
import httpx
import hmac
import hashlib
import json
import threading
from datetime import datetime, timezone

from . import settings_manager

# Use a single, shared async client for performance.
async_client = httpx.AsyncClient()

async def send_notification(event_type: str, data: dict):
    """
    Constructs and sends a webhook notification based on global settings.
    Supports both JSON and form-urlencoded content types, with optional signing.
    """
    if not settings_manager.get_setting('notifications_enabled'):
        return

    webhook_url = settings_manager.get_setting('notifications_webhook_url')
    if not webhook_url:
        print("Notification Service: Aborting send. Webhook URL is not configured.")
        return

    # --- START: MODIFICATION (Handle optional secret and content-type) ---
    secret = settings_manager.get_setting('notifications_secret')
    content_type = settings_manager.get_setting('notifications_content_type', 'application/json')

    # 1. Construct the base payload
    payload = {
        'event_type': event_type,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': data
    }
    
    headers = {}
    request_kwargs = {'timeout': 10.0}

    # 2. Prepare payload and headers based on Content-Type
    if content_type == 'application/x-www-form-urlencoded':
        # Flatten the payload for form submission. Nested 'data' dict becomes a JSON string.
        form_data = {
            'event_type': payload['event_type'],
            'timestamp': payload['timestamp'],
            'data': json.dumps(payload['data']) # Convert nested dict to JSON string
        }
        request_kwargs['data'] = form_data
        
        # Note: Signing is more complex for form data as canonical representation can vary.
        # We will sign the raw JSON representation before it's flattened for consistency.
        if secret:
            payload_for_signing = json.dumps(payload).encode('utf-8')
    else: # Default to application/json
        json_payload_bytes = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        request_kwargs['content'] = json_payload_bytes
        if secret:
            payload_for_signing = json_payload_bytes

    # 3. Add signature header ONLY if a secret is configured
    if secret:
        signature_hash = hmac.new(secret.encode('utf-8'), payload_for_signing, hashlib.sha256)
        signature = signature_hash.hexdigest()
        headers['X-Webhook-Signature-256'] = f"sha256={signature}"
    
    request_kwargs['headers'] = headers
    # --- END: MODIFICATION ---

    # 4. Send the request asynchronously
    try:
        response = await async_client.post(webhook_url, **request_kwargs)
        response.raise_for_status() 
        print(f"Notification Sent: Event '{event_type}' to {webhook_url} as {content_type}. Status: {response.status_code}")
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