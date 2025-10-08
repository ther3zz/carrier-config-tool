# --- START OF FILE routes/notifications.py ---

from flask import Blueprint, jsonify
from utils import notification_service
from utils import settings_manager

# Create a Blueprint for notification-related API routes
notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

@notifications_bp.route('/test', methods=['POST'])
def test_notification():
    """
    An endpoint to trigger a test webhook notification.
    """
    if not settings_manager.get_setting('notifications_enabled'):
        return jsonify({"error": "Notifications are not enabled in the settings."}), 400

    webhook_url = settings_manager.get_setting('notifications_webhook_url')
    if not webhook_url:
        return jsonify({"error": "Webhook URL is not configured."}), 400

    # Fire and forget the test event
    test_payload = {
        "service": "Vendor API Configuration Tool",
        "message": "This is a test notification to verify your webhook endpoint.",
        "status": "Success"
    }
    notification_service.fire_and_forget("test.event", test_payload)

    return jsonify({"message": f"Test notification has been dispatched to {webhook_url}. Check your endpoint to verify receipt."}), 202
# --- END OF FILE routes/notifications.py ---