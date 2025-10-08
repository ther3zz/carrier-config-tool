# --- START OF FILE utils/notification_service.py ---

import asyncio
import httpx
import hmac
import hashlib
import json
from datetime import datetime, timezone

from . import settings_manager

# Use a single, shared async client for performance.
# This avoids the overhead of creating a new connection for every notification.
async_client = httpx.AsyncClient()

async def send_notification(event_type: str, data: dict):
    """
    Constructs and sends a webhook notification if the feature is enabled.

    This function runs asynchronously and does not block the main thread.
    It handles payload signing, headers, and robust error catching.

    Args:
        event_type (str): The type of event (e.g., 'subaccount.created', 'did.provisioned').
        data (dict): The payload containing details about the event.
    """
    # 1. Check if notifications are enabled in settings
    if not settings_manager.get_setting('notifications_enabled'):
        return

    # 2. Get required settings for the webhook
    webhook_url = settings_manager.get_setting('notifications_webhook_url')
    secret = settings_manager.get_setting('notifications_secret')

    if not webhook_url or not secret:
        print("Notification Service: Aborting send. Webhook URL or Secret is not configured.")
        return

    # 3. Construct the full, standardized payload
    payload = {
        'event_type': event_type,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': data
    }
    
    # Convert payload to a JSON string (and then bytes) for the signing process
    payload_bytes = json.dumps(payload).encode('utf-8')

    # 4. Generate the HMAC-SHA256 signature using the secret
    signature_hash = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256)
    signature = signature_hash.hexdigest()

    # 5. Prepare the required headers for the request
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature-256': f"sha256={signature}"
    }

    # 6. Send the request asynchronously
    try:
        response = await async_client.post(webhook_url, content=payload_bytes, headers=headers, timeout=10.0)
        
        # Raise an exception for non-2xx responses to catch endpoint errors
        response.raise_for_status() 
        
        print(f"Notification Sent: Event '{event_type}' to {webhook_url}. Status: {response.status_code}")

    except httpx.RequestError as e:
        # This catches network errors like timeouts, connection refused, etc.
        print(f"Notification Error: Failed to send event '{event_type}' to {webhook_url}. Details: {e}")
    except Exception as e:
        # This catches any other unexpected errors during the process
        print(f"Notification Error: An unexpected error occurred while sending webhook. Details: {e}")


def fire_and_forget(event_type: str, data: dict):
    """
    A synchronous wrapper to schedule the async notification without blocking.
    This is crucial for calling the async notification service from synchronous
    code like your Flask routes.
    """
    try:
        # Get the running event loop or create a new one if none exists
        loop = asyncio.get_running_loop()
    except RuntimeError:  # 'get_running_loop' fails if no loop is running
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Schedule the task to run in the background
    loop.create_task(send_notification(event_type, data))

# --- END OF FILE utils/notification_service.py ---