# --- START OF FILE utils/notification_service.py ---

import asyncio
import httpx
import hmac
import hashlib
import json
import threading # <-- Import threading
from datetime import datetime, timezone

from . import settings_manager

# Use a single, shared async client for performance.
async_client = httpx.AsyncClient()

async def send_notification(event_type: str, data: dict):
    """
    Constructs and sends a webhook notification if the feature is enabled.

    This function runs asynchronously and does not block the main thread.
    It handles payload signing, headers, and robust error catching.
    """
    if not settings_manager.get_setting('notifications_enabled'):
        return

    webhook_url = settings_manager.get_setting('notifications_webhook_url')
    secret = settings_manager.get_setting('notifications_secret')

    if not webhook_url or not secret:
        print("Notification Service: Aborting send. Webhook URL or Secret is not configured.")
        return

    payload = {
        'event_type': event_type,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': data
    }
    
    payload_bytes = json.dumps(payload).encode('utf-8')
    signature_hash = hmac.new(secret.encode('utf-8'), payload_bytes, hashlib.sha256)
    signature = signature_hash.hexdigest()

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature-256': f"sha256={signature}"
    }

    try:
        # The actual async request
        response = await async_client.post(webhook_url, content=payload_bytes, headers=headers, timeout=10.0)
        response.raise_for_status() 
        print(f"Notification Sent: Event '{event_type}' to {webhook_url}. Status: {response.status_code}")
    except httpx.RequestError as e:
        print(f"Notification Error: Failed to send event '{event_type}' to {webhook_url}. Details: {e}")
    except Exception as e:
        print(f"Notification Error: An unexpected error occurred while sending webhook. Details: {e}")


# --- START: MODIFICATION (Replace asyncio loop logic with threading) ---

def _run_async_in_thread(coro):
    """
    Helper function to run an async coroutine in a new event loop.
    This function is the target for our new thread.
    """
    # asyncio.run() automatically creates a new event loop, runs the coroutine
    # until it's complete, and then closes the loop.
    asyncio.run(coro)

def fire_and_forget(event_type: str, data: dict):
    """
    A synchronous wrapper that starts the async notification in a separate
    background thread, allowing the main Flask thread to return immediately.
    """
    # Create the coroutine object we want to run
    coroutine = send_notification(event_type, data)
    
    # Create a new thread to run the coroutine.
    # The `_run_async_in_thread` function will handle the event loop for this thread.
    thread = threading.Thread(target=_run_async_in_thread, args=(coroutine,))
    
    # Daemon threads are automatically killed when the main program exits.
    thread.daemon = True
    
    # Start the thread. This call is non-blocking.
    thread.start()

# --- END: MODIFICATION ---

# --- END OF FILE utils/notification_service.py ---