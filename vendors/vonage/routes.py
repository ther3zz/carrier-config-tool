# --- START OF FILE vendors/vonage/routes.py ---

import os
from flask import Blueprint, request, jsonify
from . import client # Import client functions from the same package
from utils import credentials_manager
from utils.config_loader import load_config_file
from utils import settings_manager

vonage_bp = Blueprint('vonage', __name__, url_prefix='/api/vonage')

# Define path to config file
NPA_DATA_CONFIG_FILE = os.path.join('config', 'npa_data.json')

# --- Credentials Helper Function (Unchanged) ---
def _get_credentials_from_request(data: dict, use_primary_keys: bool = False) -> (dict, tuple):
    """
    Helper to extract credentials from a request payload. It now handles cases
    where the function needs 'primary_api_key' instead of 'username'/'api_key'.
    """
    account_name = data.get('account_name')
    master_key = data.get('master_key')

    key_name = 'primary_api_key' if use_primary_keys else 'api_key'
    secret_name = 'primary_api_secret' if use_primary_keys else 'api_secret'

    if account_name and master_key:
        try:
            creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
            return {key_name: creds['api_key'], secret_name: creds['api_secret']}, None
        except ValueError as e:
            return None, ({"error": str(e)}, 401)

    username = data.get('username') or data.get('primary_api_key')
    password = data.get('password') or data.get('primary_api_secret')

    if username and password:
        return {key_name: username, secret_name: password}, None

    error_msg = "Missing credentials. Please provide 'account_name' and 'master_key', or the appropriate API key and secret."
    return None, ({"error": error_msg}, 400)


# --- Subaccount Management, PSIP, and other DID Routes are unchanged ---
@vonage_bp.route('/subaccounts/list', methods=['POST'])
def handle_vonage_list_subaccounts():
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400

    credentials, error = _get_credentials_from_request(data, use_primary_keys=True)
    if error: return jsonify(error[0]), error[1]

    result_data, status_code = client.list_subaccounts(credentials['primary_api_key'], credentials['primary_api_secret'], log_enabled=log_enabled)
    response_body = {"status_code": status_code, "data": result_data}
    if status_code >= 400: response_body = {"status_code": status_code, **result_data}
    return jsonify(response_body), status_code

# ... (all other existing endpoints remain the same) ...

@vonage_bp.route('/update_did', methods=['POST'])
def handle_vonage_update_did():
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    treat_420_as_success = settings_manager.get_setting('treat_420_as_success_configure')
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    country = data.get('country')
    msisdn = data.get('msisdn')
    if not country or not msisdn: return jsonify({"error": "Missing 'country' or 'msisdn' for update", "msisdn": msisdn}), 400
    credentials, error = _get_credentials_from_request(data)
    if error: return jsonify(error[0]), error[1]
    config = data.get('config', {})
    result_data, status_code = client.update_did(credentials['api_key'], credentials['api_secret'], country, msisdn, config, log_enabled=log_enabled, treat_420_as_success=treat_420_as_success)
    response_body = {"status_code": status_code, **result_data}
    return jsonify(response_body), status_code

# --- START: MODIFICATION (Add Cancel DID Endpoint for UI) ---
@vonage_bp.route('/cancel_did', methods=['POST'])
def handle_vonage_cancel_did():
    """
    Endpoint for the UI to cancel a single DID. This is called in a loop by the frontend.
    """
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    country = data.get('country')
    msisdn = data.get('msisdn')
    if not country or not msisdn:
        return jsonify({"error": "Missing 'country' or 'msisdn' for cancellation", "msisdn": msisdn}), 400

    # Get credentials for this specific request
    credentials, error = _get_credentials_from_request(data)
    if error:
        return jsonify(error[0]), error[1]

    # Call the client function to cancel the single DID
    result_data, status_code = client.cancel_did(
        credentials['api_key'], 
        credentials['api_secret'], 
        country, 
        msisdn,
        log_enabled=log_enabled
    )

    response_body = {"status_code": status_code, **result_data}
    return jsonify(response_body), status_code
# --- END: MODIFICATION ---

@vonage_bp.route('/find_dids_for_npa', methods=['POST'])
def handle_vonage_find_dids_for_npa():
    # (Function unchanged)
    log_enabled = settings_manager.get_setting('store_logs_enabled')
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    npa = data.get('npa')
    quantity = data.get('quantity', 1)
    if not npa or not isinstance(npa, str) or len(npa) != 3: return jsonify({"error": "Invalid NPA format. Must be a 3-digit string.", "npa": npa}), 400
    if not isinstance(quantity, int) or not 1 <= quantity <= 100: return jsonify({"error": "Quantity must be an integer between 1 and 100.", "npa": npa}), 400
    credentials, error = _get_credentials_from_request(data)
    if error: return jsonify(error[0]), error[1]
    npa_data = load_config_file(NPA_DATA_CONFIG_FILE)
    if not npa_data: return jsonify({"error": "NPA data configuration file not found or is empty.", "npa": npa}), 500
    country = 'US' if npa in npa_data.get('US', []) else 'CA' if npa in npa_data.get('CA', []) else None
    if not country: return jsonify({"error": f"NPA '{npa}' not found in US or CA data.", "npa": npa, "data": {"numbers": [], "count": 0, "npa": npa}}), 404
    search_params = { 'country': country, 'features': 'VOICE', 'pattern': f"1{npa}", 'search_pattern': 0, 'size': quantity }
    result_data, status_code = client.search_dids(credentials['api_key'], credentials['api_secret'], search_params, log_enabled=log_enabled)
    if isinstance(result_data, dict): result_data['npa'] = npa
    response_body = {"status_code": status_code, "data": result_data}
    if status_code >= 400: response_body = {"status_code": status_code, **result_data}
    return jsonify(response_body), status_code

# --- END OF FILE vendors/vonage/routes.py ---