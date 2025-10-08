# --- START OF FILE vendors/vonage/routes.py ---

from flask import Blueprint, request, jsonify
from utils import credentials_manager
from utils import settings_manager
# --- START: MODIFICATION ---
from utils.password_generator import generate_secure_secret
# --- END: MODIFICATION ---
from . import client as vonage_client

# Create a Blueprint for all Vonage-related API routes that the UI will call
vonage_bp = Blueprint('vonage', __name__, url_prefix='/api/vonage')

def _get_credentials_from_request(data: dict):
    """Helper to consistently extract and decrypt credentials from a request payload."""
    master_key = data.get('master_key')
    account_name = data.get('account_name')
    
    if not master_key or not account_name:
        raise ValueError("Master Key and Account Name are required.")
        
    # Use the master key to get the decrypted API key and secret
    return credentials_manager.get_decrypted_credentials(account_name, master_key)


# --- Subaccount Management Endpoints ---

@vonage_bp.route('/subaccounts', methods=['POST'])
def get_subaccounts():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        result, status_code = vonage_client.list_subaccounts(
            primary_api_key=creds['api_key'],
            primary_api_secret=creds['api_secret'],
            log_enabled=log_enabled
        )
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# --- START: MODIFICATION (Update create_subaccount logic) ---
@vonage_bp.route('/subaccounts/create', methods=['POST'])
def create_subaccount():
    data = request.get_json()
    try:
        # We need the master key to save the new credential later
        master_key = data.get('master_key')
        if not master_key:
            raise ValueError("Master Key is required to create and save a new subaccount.")
            
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')

        # Generate a secret if the user left the field blank
        secret = data.get('secret')
        if not secret:
            secret = generate_secure_secret()

        # Extract subaccount creation specific data
        payload = {
            "name": data.get('name'),
            "secret": secret,
            "use_primary_account_balance": data.get('use_primary_balance', True)
        }
        
        # Call the Vonage client to create the subaccount
        result, status_code = vonage_client.create_subaccount(
            primary_api_key=creds['api_key'],
            primary_api_secret=creds['api_secret'],
            payload=payload,
            log_enabled=log_enabled
        )
        
        # If creation was successful, save the new credentials to our database
        if status_code < 400:
            new_sub_name = result.get('name')
            new_sub_api_key = result.get('api_key')
            
            if new_sub_name and new_sub_api_key:
                try:
                    # Save the new credential using the name, new API key, and the secret we used
                    credentials_manager.save_credential(
                        name=new_sub_name,
                        api_key=new_sub_api_key,
                        api_secret=secret, # Use the same secret we sent to the API
                        master_key=master_key
                    )
                    result['message'] = f"Successfully created subaccount '{new_sub_name}' and saved its credentials locally."
                except Exception as e:
                    # If saving fails, inform the user. The subaccount exists on Vonage's side.
                    result['message'] = (f"WARNING: Successfully created subaccount '{new_sub_name}' via Vonage API, "
                                       f"but FAILED to save its credentials locally. Please add them manually. Error: {str(e)}")
                    # Change the status code to indicate a partial success/warning to the client
                    status_code = 207 # Multi-Status
            else:
                result['message'] = "Subaccount created, but API response was missing name or API key. Could not save locally."
        
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
# --- END: MODIFICATION ---

@vonage_bp.route('/subaccounts/update', methods=['POST'])
def update_subaccount():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        payload = {
            "name": data.get('name'),
            "suspended": data.get('suspended')
        }
        subaccount_key = data.get('subaccount_key')
        
        result, status_code = vonage_client.update_subaccount(
            primary_api_key=creds['api_key'],
            primary_api_secret=creds['api_secret'],
            subaccount_key=subaccount_key,
            payload=payload,
            log_enabled=log_enabled
        )
        if status_code < 400:
            result['message'] = f"Successfully updated subaccount '{result.get('name')}'."
            
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


# --- DID Management Endpoints ---

@vonage_bp.route('/dids/search', methods=['POST'])
def search_dids():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        params = {
            "country": data.get('country'),
            "type": data.get('type'),
            "pattern": data.get('pattern'),
            "search_pattern": data.get('search_pattern'),
            "features": data.get('features')
        }
        
        result, status_code = vonage_client.search_dids(
            username=creds['api_key'],
            password=creds['api_secret'],
            params=params,
            log_enabled=log_enabled
        )
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@vonage_bp.route('/dids/buy', methods=['POST'])
def buy_did():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        result, status_code = vonage_client.buy_did(
            username=creds['api_key'],
            password=creds['api_secret'],
            country=data.get('country'),
            msisdn=data.get('msisdn'),
            target_api_key=data.get('target_api_key'),
            log_enabled=log_enabled,
            treat_420_as_success=settings_manager.get_setting('treat_420_as_success_buy'),
            verify_on_420=settings_manager.get_setting('verify_on_420_buy')
        )
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@vonage_bp.route('/dids/update', methods=['POST'])
def update_did():
    data = request.get_json()
    try:
        # This can handle manual entry or stored credentials
        if data.get('account_name'):
            creds = _get_credentials_from_request(data)
        else:
            creds = {'api_key': data.get('username'), 'api_secret': data.get('password')}
            if not creds['api_key'] or not creds['api_secret']:
                raise ValueError("Manual entry requires both API Key and Secret.")

        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        result, status_code = vonage_client.update_did(
            username=creds['api_key'],
            password=creds['api_secret'],
            country=data.get('country'),
            msisdn=data.get('msisdn'),
            config=data.get('config'),
            log_enabled=log_enabled,
            treat_420_as_success=settings_manager.get_setting('treat_420_as_success_configure')
        )
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
        
@vonage_bp.route('/dids/release', methods=['POST'])
def release_did():
    data = request.get_json()
    try:
        # Release can also use manual or stored creds
        if data.get('account_name'):
            creds = _get_credentials_from_request(data)
        else:
            creds = {'api_key': data.get('username'), 'api_secret': data.get('password')}
            if not creds['api_key'] or not creds['api_secret']:
                raise ValueError("Manual entry requires both API Key and Secret.")

        log_enabled = settings_manager.get_setting('store_logs_enabled')

        result, status_code = vonage_client.cancel_did(
            username=creds['api_key'],
            password=creds['api_secret'],
            country=data.get('country'),
            msisdn=data.get('msisdn'),
            log_enabled=log_enabled
        )
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


# Add stubs for other UI functions if they have corresponding backend calls.
# The current JS file seems to call endpoints that are covered above.
# If you add more UI features (like PSIP trunking from the UI), their endpoints would go here.

# --- END OF FILE vendors/vonage/routes.py ---