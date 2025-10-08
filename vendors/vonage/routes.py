# --- START OF FILE vendors/vonage/routes.py ---

from flask import Blueprint, request, jsonify
from utils import credentials_manager
from utils import settings_manager
from utils.password_generator import generate_secure_secret
from . import client as vonage_client

# Create a Blueprint for all Vonage-related API routes that the UI will call
vonage_bp = Blueprint('vonage', __name__, url_prefix='/api/vonage')

def _get_credentials_from_request(data: dict):
    """Helper to consistently extract and decrypt credentials from a request payload."""
    master_key = data.get('master_key')
    
    # Handle manual entry vs. stored credential
    if data.get('account_name') and data.get('account_name') != 'manual':
        account_name = data.get('account_name')
        if not master_key or not account_name:
            raise ValueError("Master Key and Account Name are required.")
        return credentials_manager.get_decrypted_credentials(account_name, master_key)
    else:
        # Assumes manual entry if account_name is not provided or is 'manual'
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            raise ValueError("Manual entry requires both API Key and API Secret.")
        return {'api_key': username, 'api_secret': password}


# --- Subaccount Management Endpoints ---

@vonage_bp.route('/subaccounts', methods=['POST'])
def get_subaccounts():
    data = request.get_json()
    try:
        # This endpoint specifically uses stored primary account credentials
        master_key = data.get('master_key')
        account_name = data.get('account_name')
        if not master_key or not account_name:
            raise ValueError("A stored Primary Account credential is required.")

        creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
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

@vonage_bp.route('/subaccounts/create', methods=['POST'])
def create_subaccount():
    data = request.get_json()
    try:
        master_key = data.get('master_key')
        account_name = data.get('account_name')
        if not master_key or not account_name:
            raise ValueError("A stored Primary Account credential and Master Key are required.")
            
        creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
        log_enabled = settings_manager.get_setting('store_logs_enabled')

        secret = data.get('secret')
        if not secret:
            secret = generate_secure_secret()

        payload = {
            "name": data.get('name'),
            "secret": secret,
            "use_primary_account_balance": data.get('use_primary_balance', True)
        }
        
        result, status_code = vonage_client.create_subaccount(
            primary_api_key=creds['api_key'],
            primary_api_secret=creds['api_secret'],
            payload=payload,
            log_enabled=log_enabled
        )
        
        if status_code < 400:
            new_sub_name = result.get('name')
            new_sub_api_key = result.get('api_key')
            
            if new_sub_name and new_sub_api_key:
                try:
                    credentials_manager.save_credential(
                        name=new_sub_name,
                        api_key=new_sub_api_key,
                        api_secret=secret,
                        master_key=master_key
                    )
                    result['message'] = f"Successfully created subaccount '{new_sub_name}' and saved its credentials locally."
                except Exception as e:
                    result['message'] = (f"WARNING: Successfully created subaccount '{new_sub_name}' via Vonage API, "
                                       f"but FAILED to save its credentials locally. Please add them manually. Error: {str(e)}")
                    status_code = 207
            else:
                result['message'] = "Subaccount created, but API response was missing name or API key. Could not save locally."
        
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@vonage_bp.route('/subaccounts/update', methods=['POST'])
def update_subaccount():
    data = request.get_json()
    try:
        master_key = data.get('master_key')
        account_name = data.get('account_name')
        if not master_key or not account_name:
            raise ValueError("A stored Primary Account credential is required.")

        creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
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


# --- START: MODIFICATION (Add PSIP Trunking Endpoints) ---
@vonage_bp.route('/psip/create', methods=['POST'])
def create_psip_domain():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')

        # Extract only the PSIP-specific payload keys
        payload = {
            'name': data.get('name'),
            'trunk_name': data.get('trunk_name'),
            'tls': data.get('tls'),
            'digest_auth': data.get('digest_auth'),
            'srtp': data.get('srtp'),
            'acl': data.get('acl', []),
            'domain_type': data.get('domain_type')
        }

        result, status_code = vonage_client.create_psip(
            username=creds['api_key'],
            password=creds['api_secret'],
            payload=payload,
            log_enabled=log_enabled
        )
        # Add a clear message for the UI
        if status_code < 400:
            result['message'] = f"Successfully sent PSIP domain creation request for '{payload.get('name')}'."
            result['status_code'] = status_code

        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

@vonage_bp.route('/psip', methods=['POST'])
def get_psip_domains():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        result, status_code = vonage_client.get_psip_domains(
            username=creds['api_key'],
            password=creds['api_secret'],
            log_enabled=log_enabled
        )
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
# --- END: MODIFICATION ---


# --- DID Management Endpoints ---

@vonage_bp.route('/dids/search', methods=['POST'])
def search_dids():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        # Extract only the search-specific params
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
        creds = _get_credentials_from_request(data)
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
        creds = _get_credentials_from_request(data)
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
# --- END OF FILE vendors/vonage/routes.py ---