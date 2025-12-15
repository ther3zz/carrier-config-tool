from flask import Blueprint, request, jsonify
from utils import credentials_manager
from utils import settings_manager
from utils.password_generator import generate_secure_secret
from utils import notification_service
from utils import logger
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
        creds = credentials_manager.get_decrypted_credentials(account_name, master_key)
        # Add account_name to the returned dict for later use
        creds['account_name'] = account_name
        return creds
    else:
        # Assumes manual entry if account_name is not provided or is 'manual'
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            raise ValueError("Manual entry requires both API Key and API Secret.")
        return {'api_key': username, 'api_secret': password, 'account_name': 'Manual Entry'}


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

                    notification_payload = {
                        "primary_account": account_name,
                        "subaccount_name": new_sub_name,
                        "subaccount_api_key": new_sub_api_key,
                        "use_primary_balance": payload['use_primary_account_balance']
                    }
                    notification_service.fire_and_forget("subaccount.created", notification_payload)

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


# --- PSIP Trunking Endpoints ---
def _get_psip_form_payload(data: dict) -> dict:
    """Helper to extract PSIP domain payload from a request."""
    return {
        'name': data.get('name'),
        'trunk_name': data.get('trunk_name'),
        'tls': data.get('tls'),
        'digest_auth': data.get('digest_auth'),
        'srtp': data.get('srtp'),
        'acl': data.get('acl', []),
        'domain_type': data.get('domain_type')
    }


@vonage_bp.route('/psip/create', methods=['POST'])
def create_psip_domain():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        
        payload = _get_psip_form_payload(data)
        

        result, status_code = vonage_client.create_psip(
            username=creds['api_key'],
            password=creds['api_secret'],
            payload=payload,
            log_enabled=log_enabled
        )
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


@vonage_bp.route('/psip/update', methods=['POST'])
def update_psip_domain():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        domain_name = data.get('original_domain_name')
        if not domain_name:
            return jsonify({"error": "Original domain name is required for update."}), 400

        payload = _get_psip_form_payload(data)

        result, status_code = vonage_client.update_psip_domain(
            username=creds['api_key'],
            password=creds['api_secret'],
            domain_name=domain_name,
            payload=payload,
            log_enabled=log_enabled
        )

        if status_code < 400:
            result['message'] = f"Successfully updated PSIP domain '{payload.get('name')}'."
        
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

@vonage_bp.route('/psip/delete', methods=['POST'])
def delete_psip_domain():
    data = request.get_json()
    try:
        creds = _get_credentials_from_request(data)
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        domain_name = data.get('domain_name')
        if not domain_name:
            return jsonify({"error": "Domain name is required for deletion."}), 400

        result, status_code = vonage_client.delete_psip_domain(
            username=creds['api_key'],
            password=creds['api_secret'],
            domain_name=domain_name,
            log_enabled=log_enabled
        )
        
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500



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
        # NOTE: Provisioning notification is handled by fastapi_app.py or in a future UI-based task.
        # This endpoint is generally part of a larger workflow.
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

        if status_code < 400:
            notification_payload = {
                "account_name": creds.get('account_name'),
                "subaccount_api_key": creds.get('api_key'),
                "did": data.get('msisdn'),
                "country": data.get('country')
            }
            notification_service.fire_and_forget("did.released", notification_payload)

        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

from concurrent.futures import ThreadPoolExecutor, as_completed

def _check_ownership_single(number, creds, log_enabled):
    """
    Checks if a single number exists in a subaccount.
    Returns the result dict.
    """
    # Using the verify_did_ownership function from the client
    is_owned, response_data = vonage_client._verify_did_ownership(
        username=creds['api_key'], 
        password=creds['api_secret'], 
        msisdn=number, 
        log_enabled=log_enabled
    )
    
    # Log the check if enabled
    if log_enabled:
        logger.log_request_response(
            operation_name=f"CheckOwnership[{number}]",
            request_details={"msisdn": number},
            response_data=response_data,
            status_code=200 if is_owned else 404,
            account_id=creds.get('account_name')
        )
    
    if is_owned:
        return {
            'number': number,
            'status': 'found',
            'subaccount': creds.get('api_key'),
            'friendly_name': creds.get('account_name')
        }
    return None

@vonage_bp.route('/dids/search_ownership', methods=['POST'])
def search_did_ownership_batch():
    data = request.get_json()
    # Log incoming system request
    # Since this is Flask, we need to construct a pseudo-request object or just pass data if logger supports it, 
    # but logger.log_incoming_request expects a FastAPI Request object. 
    # We will log manually to system logger for Flask.
    try:
        if settings_manager.get_setting('store_logs_enabled'):
             import logging
             system_logger = logging.getLogger()
             system_logger.info(f"Incoming Flask Request: POST /api/vonage/dids/search_ownership - Payload keys: {list(data.keys())}")

        # We need a master key to decrypt ALL credentials
        master_key = data.get('master_key')
        if not master_key:
             return jsonify({"error": "Master Key is required to search across all subaccounts."}), 400
             
        numbers = data.get('numbers', [])
        if not numbers:
             return jsonify({"error": "No numbers provided."}), 400
             
        log_enabled = settings_manager.get_setting('store_logs_enabled')
        
        # 1. Get ALL credentials
        all_creds_dict = credentials_manager.get_all_credentials()
        
        # 2. Decrypt them all
        decrypted_creds_list = []
        for name, cred_data in all_creds_dict.items():
            try:
                # We need to manually decrypt since get_all_credentials returns encrypted secrets
                from utils import encryption # Lazy import to avoid circular dependency if any
                decrypted_secret = encryption.decrypt_data(cred_data['encrypted_secret'], master_key)
                decrypted_creds_list.append({
                    'account_name': name,
                    'api_key': cred_data['api_key'],
                    'api_secret': decrypted_secret
                })
            except Exception:
                # If decryption fails (e.g. wrong key, though unlikely if key worked for others), skip
                continue
        
        if not decrypted_creds_list:
             return jsonify({"error": "No credentials could be decrypted. Check Master Key or store credentials first."}), 400

        # 3. Perform Search
        results = []
        
        max_threads = 10 # Control concurrency
        
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_search = {}
            
            for number in numbers:
                # Sanitize
                clean_number = "".join(filter(str.isdigit, number))
                if not clean_number: continue
                
                # Start with 'not_found'
                results.append({
                    'number': clean_number, 
                    'status': 'not_found', 
                    'subaccount': None, 
                    'friendly_name': None
                })
                current_result_idx = len(results) - 1
                
                for creds in decrypted_creds_list:
                    future = executor.submit(_check_ownership_single, clean_number, creds, log_enabled)
                    future_to_search[future] = current_result_idx

            for future in as_completed(future_to_search):
                idx = future_to_search[future]
                try:
                    found_data = future.result()
                    if found_data:
                        # Update the result at idx
                        results[idx] = found_data
                except Exception as e:
                    print(f"Error checking ownership: {e}")
                    
        return jsonify({'results': results}), 200

    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
