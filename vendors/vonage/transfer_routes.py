# --- START OF FILE vendors/vonage/transfer_routes.py ---

"""
Dedicated Flask Blueprint for DID transfer operations between Vonage subaccounts.

Security layers (executed in order for each transfer):
  1. Input validation — required fields, format checks
  2. Credential decryption — primary account via master key
  3. Subaccount validation — verify from/to are real subaccounts under primary
  4. Ownership verification — confirm source actually owns the number
  5. Execute transfer — call Vonage transfer API
  6. Notification — fire did.transferred event on success
"""

import re
from flask import Blueprint, request, jsonify
from utils import credentials_manager
from utils import settings_manager
from utils import notification_service
from . import client as vonage_client

vonage_transfer_bp = Blueprint('vonage_transfer', __name__, url_prefix='/api/vonage/dids')

# --- Input Validation Helpers ---

_API_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9]+$')
_MSISDN_PATTERN = re.compile(r'^\d{10,15}$')
_COUNTRY_PATTERN = re.compile(r'^[A-Za-z]{2}$')


def _validate_transfer_inputs(data):
    """
    Validates and sanitises transfer request inputs.
    Returns (cleaned_data, error_message) — error_message is None on success.
    """
    from_key = (data.get('from_api_key') or '').strip()
    to_key = (data.get('to_api_key') or '').strip()
    number = (data.get('number') or '').strip()
    country = (data.get('country') or '').strip().upper()

    if not from_key or not to_key or not number or not country:
        return None, "All fields are required: from_api_key, to_api_key, number, country."

    if not _API_KEY_PATTERN.match(from_key):
        return None, "Invalid 'from_api_key' format. Must be alphanumeric."

    if not _API_KEY_PATTERN.match(to_key):
        return None, "Invalid 'to_api_key' format. Must be alphanumeric."

    # Sanitise number to digits only
    clean_number = re.sub(r'\D', '', number)
    if not _MSISDN_PATTERN.match(clean_number):
        return None, f"Invalid number format: '{number}'. Must be 10-15 digits."

    if not _COUNTRY_PATTERN.match(country):
        return None, f"Invalid country code: '{country}'. Must be 2 letters (ISO 3166-1 alpha-2)."

    if from_key == to_key:
        return None, "Source and destination subaccounts cannot be the same."

    return {
        'from_api_key': from_key,
        'to_api_key': to_key,
        'number': clean_number,
        'country': country
    }, None


def _validate_subaccount_membership(primary_api_key, primary_api_secret, target_api_key, subaccounts_cache, log_enabled):
    """
    Verifies that a given API key belongs to a subaccount under the primary account.
    Uses a cache dict so list_subaccounts() is only called once per request.
    Returns (is_valid, subaccounts_cache, error_message).
    """
    # Populate cache on first call
    if subaccounts_cache is None:
        result, status_code = vonage_client.list_subaccounts(
            primary_api_key=primary_api_key,
            primary_api_secret=primary_api_secret,
            log_enabled=log_enabled
        )
        if status_code >= 400:
            return False, None, f"Failed to fetch subaccounts for validation: {result.get('error', 'Unknown error')}"

        subaccounts_list = result.get('subaccounts', [])
        # Build set of valid API keys (subaccounts + primary account itself)
        subaccounts_cache = {sub.get('api_key') for sub in subaccounts_list if sub.get('api_key')}
        subaccounts_cache.add(primary_api_key)

    if target_api_key not in subaccounts_cache:
        return False, subaccounts_cache, f"API key '{target_api_key}' is not a valid subaccount under this primary account."

    return True, subaccounts_cache, None


# --- Transfer Endpoint ---

@vonage_transfer_bp.route('/transfer', methods=['POST'])
def transfer_did():
    """
    Transfers a single phone number from one subaccount to another.
    
    Full security pipeline:
      1. Input validation
      2. Primary account credential decryption
      3. Subaccount membership validation (from + to)
      4. Ownership verification on source account
      5. Execute Vonage transfer API call
      6. Fire notification on success
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload."}), 400

    try:
        # --- Step 1: Input Validation ---
        master_key = data.get('master_key')
        account_name = data.get('account_name')
        if not master_key or not account_name:
            raise ValueError("Master Key and Primary Account name are required.")

        cleaned, validation_error = _validate_transfer_inputs(data)
        if validation_error:
            return jsonify({"error": validation_error}), 400

        # --- Step 2: Decrypt Primary Account Credentials ---
        primary_creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
        log_enabled = settings_manager.get_setting('store_logs_enabled')

        # --- Step 3: Subaccount Validation ---
        # Verify both from and to are real subaccounts under this primary account
        subaccounts_cache = None

        is_valid, subaccounts_cache, error = _validate_subaccount_membership(
            primary_creds['api_key'], primary_creds['api_secret'],
            cleaned['from_api_key'], subaccounts_cache, log_enabled
        )
        if not is_valid:
            return jsonify({"error": f"Source validation failed: {error}"}), 400

        is_valid, subaccounts_cache, error = _validate_subaccount_membership(
            primary_creds['api_key'], primary_creds['api_secret'],
            cleaned['to_api_key'], subaccounts_cache, log_enabled
        )
        if not is_valid:
            return jsonify({"error": f"Destination validation failed: {error}"}), 400

        # --- Step 4: Ownership Verification ---
        # Verify the source subaccount actually owns this number before transferring.
        # We need the source subaccount's credentials for the ownership check.
        # Try to find them in the credential store; if not found, skip verification
        # but log a warning (the Vonage API will still reject invalid transfers).
        ownership_verified = False
        try:
            # Look up source subaccount credentials from the store
            all_creds = credentials_manager.get_all_credentials()
            source_cred_entry = None
            for name, cred_data in all_creds.items():
                if cred_data.get('api_key') == cleaned['from_api_key']:
                    source_cred_entry = (name, cred_data)
                    break

            if source_cred_entry:
                from utils.encryption import decrypt_data
                source_secret = decrypt_data(source_cred_entry[1]['encrypted_secret'], master_key)
                is_owned, _ = vonage_client._verify_did_ownership(
                    username=cleaned['from_api_key'],
                    password=source_secret,
                    msisdn=cleaned['number'],
                    log_enabled=log_enabled
                )
                if not is_owned:
                    return jsonify({
                        "error": f"Number {cleaned['number']} is not owned by source subaccount {cleaned['from_api_key']}. Transfer aborted."
                    }), 404
                ownership_verified = True
            else:
                # Source subaccount not in our credential store — log warning but proceed
                # The Vonage API will reject the transfer if the number isn't on the source account.
                print(f"WARNING: Source subaccount {cleaned['from_api_key']} not found in credential store. "
                      f"Skipping pre-transfer ownership check. Vonage API will validate.")
        except Exception as e:
            # Non-fatal: ownership check is a safety net, not a blocker
            print(f"WARNING: Ownership verification encountered an error: {e}. Proceeding with transfer.")

        # --- Step 5: Execute Transfer ---
        result, status_code = vonage_client.transfer_number(
            primary_api_key=primary_creds['api_key'],
            primary_api_secret=primary_creds['api_secret'],
            from_api_key=cleaned['from_api_key'],
            to_api_key=cleaned['to_api_key'],
            number=cleaned['number'],
            country=cleaned['country'],
            log_enabled=log_enabled
        )

        # --- Step 6: Notification ---
        if status_code < 400:
            notification_payload = {
                "primary_account": account_name,
                "from_api_key": cleaned['from_api_key'],
                "to_api_key": cleaned['to_api_key'],
                "number": cleaned['number'],
                "country": cleaned['country'],
                "ownership_pre_verified": ownership_verified
            }
            notification_service.fire_and_forget("did.transferred", notification_payload)
            result['message'] = f"Successfully transferred number {cleaned['number']} from {cleaned['from_api_key']} to {cleaned['to_api_key']}."

        return jsonify(result), status_code

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# --- END OF FILE vendors/vonage/transfer_routes.py ---
