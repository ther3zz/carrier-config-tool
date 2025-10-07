# --- START OF FILE vendors/vonage/client.py ---
import requests
import json
import traceback
import time
from utils.logger import log_request_response

# Define Vonage API URLs
NEXMO_PSIP_API_URL = 'https://api.nexmo.com/v1/psip/'
NEXMO_SEARCH_API_URL = 'https://rest.nexmo.com/number/search'
NEXMO_BUY_API_URL = 'https://rest.nexmo.com/number/buy'
# --- START: MODIFICATION ---
NEXMO_CANCEL_API_URL = 'https://rest.nexmo.com/number/cancel' # New endpoint
# --- END: MODIFICATION ---
NEXMO_UPDATE_API_URL = 'https://rest.nexmo.com/number/update'
NEXMO_OWNED_API_URL = 'https://rest.nexmo.com/account/numbers'
VONAGE_ACCOUNTS_API_URL = 'https://api.nexmo.com/accounts'


def _handle_vonage_error(e, operation_name="Request"):
    """(Function unchanged)"""
    try:
        if isinstance(e, requests.exceptions.Timeout):
            print(f"{operation_name} Error: Request timed out: {e}")
            return {"error": f"{operation_name} request timed out"}, 504
        elif isinstance(e, requests.exceptions.ConnectionError):
            print(f"{operation_name} Error: Connection error: {e}")
            return {"error": f"{operation_name} connection error"}, 503
        elif isinstance(e, requests.exceptions.HTTPError):
            status_code = e.response.status_code
            error_data_text = e.response.text
            error_data_json = {}
            api_error_message = f"HTTP {status_code}"
            try:
                error_data_json = e.response.json()
                api_error_message = error_data_json.get('error-code-label') or \
                                    error_data_json.get('title') or \
                                    error_data_json.get('detail') or \
                                    str(error_data_json)
            except json.JSONDecodeError:
                api_error_message = error_data_text if error_data_text else api_error_message

            print(f"{operation_name} Error: Request failed. Status: {status_code}, API Error: '{api_error_message}', Raw Response: '{error_data_text[:200]}...'")
            return {
                "error": f"{operation_name} request failed: {api_error_message}",
                "response_data_json": error_data_json,
                "response_data_text": error_data_text
            }, status_code
        elif isinstance(e, requests.exceptions.RequestException):
            print(f"{operation_name} Error: Unexpected request exception: {e}")
            return {"error": f"Unexpected {operation_name} request error: {str(e)}"}, 500
        else:
            print(f"{operation_name} Error: Unexpected internal server error: {e}")
            traceback.print_exc()
            return {"error": f"An internal server error occurred during {operation_name} request."}, 500
    except Exception as handler_ex:
        print(f"CRITICAL ERROR in _handle_vonage_error for {operation_name}: {handler_ex}")
        traceback.print_exc()
        return {"error": "An critical internal error occurred during error handling."}, 500


# ... (create_psip, get_psip_domains, etc. are unchanged) ...
def create_psip(username, password, payload, log_enabled=False):
    operation_name = "Vonage PSIP Create"
    request_details = {"URL": NEXMO_PSIP_API_URL, "Method": "POST", "Auth": (username, password), "Payload": payload}
    response_data, status_code = None, None
    try:
        response = requests.post(NEXMO_PSIP_API_URL, auth=(username, password), json=payload, headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        try: response_data = response.json()
        except json.JSONDecodeError: response_data = {"message": "PSIP request successful, but response was not JSON.", "raw_response": response.text}
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, "PSIP")
    except Exception as e: response_data, status_code = _handle_vonage_error(e, "PSIP")
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code

def get_psip_domains(username, password, log_enabled=False):
    operation_name = "Vonage PSIP Get All Domains"
    request_details = {"URL": NEXMO_PSIP_API_URL, "Method": "GET", "Auth": (username, password)}
    response_data, status_code = None, None
    try:
        response = requests.get(NEXMO_PSIP_API_URL, auth=(username, password), headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        try: response_data = response.json()
        except json.JSONDecodeError: response_data = {"message": "PSIP get all domains request successful, but response was not JSON.", "raw_response": response.text}
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, "PSIP Get All")
    except Exception as e: response_data, status_code = _handle_vonage_error(e, "PSIP Get All")
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code

def update_psip_domain(username, password, domain_name, payload, log_enabled=False):
    operation_name = f"Vonage PSIP Update Domain ({domain_name})"
    url = f"{NEXMO_PSIP_API_URL.rstrip('/')}/{domain_name}"
    request_details = {"URL": url, "Method": "PUT", "Auth": (username, password), "Payload": payload}
    response_data, status_code = None, None
    try:
        response = requests.put(url, auth=(username, password), json=payload, headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        try: response_data = response.json()
        except json.JSONDecodeError: response_data = {"message": "PSIP update request successful, but response was not JSON.", "raw_response": response.text}
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, f"PSIP Update ({domain_name})")
    except Exception as e: response_data, status_code = _handle_vonage_error(e, f"PSIP Update ({domain_name})")
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code

def delete_psip_domain(username, password, domain_name, log_enabled=False):
    operation_name = f"Vonage PSIP Delete Domain ({domain_name})"
    url = f"{NEXMO_PSIP_API_URL.rstrip('/')}/{domain_name}"
    request_details = {"URL": url, "Method": "DELETE", "Auth": (username, password)}
    response_data, status_code = None, None
    try:
        response = requests.delete(url, auth=(username, password), headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        status_code = response.status_code
        if response.text:
            try: response_data = response.json()
            except json.JSONDecodeError: response_data = {"raw_response": response.text}
        else: response_data = {"message": f"Domain '{domain_name}' deleted successfully."}
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, f"PSIP Delete ({domain_name})")
    except Exception as e: response_data, status_code = _handle_vonage_error(e, f"PSIP Delete ({domain_name})")
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code

def search_dids(username, password, search_params, log_enabled=False):
    operation_name = "Vonage DID Search"
    request_details = {"URL": NEXMO_SEARCH_API_URL, "Method": "GET", "Auth": (username, password), "Params": search_params}
    response_data, status_code = None, None
    try:
        response = requests.get(NEXMO_SEARCH_API_URL, auth=(username, password), params=search_params, headers={'Accept': 'application/json'}, timeout=20)
        response.raise_for_status()
        try: response_data = response.json()
        except json.JSONDecodeError: response_data = {"error": f"Search failed (non-JSON response, status {response.status_code})"}
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, "Search DID")
    except Exception as e: response_data, status_code = _handle_vonage_error(e, "Search DID")
    finally:
        if isinstance(response_data, dict):
            if 'numbers' not in response_data: response_data['numbers'] = []
            if 'count' not in response_data: response_data['count'] = len(response_data['numbers'])
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code

def _verify_did_ownership(username, password, msisdn, log_enabled=False):
    operation_name = f"Vonage DID Ownership Verification ({msisdn})"
    search_params = { 'pattern': msisdn, 'search_pattern': 0, 'size': 1 }
    request_details = {"URL": NEXMO_OWNED_API_URL, "Method": "GET", "Auth": (username, password), "Params": search_params}
    response_data, status_code = None, None
    try:
        response = requests.get(NEXMO_OWNED_API_URL, auth=(username, password), params=search_params, headers={'Accept': 'application/json'}, timeout=20)
        response.raise_for_status()
        response_data = response.json()
        status_code = response.status_code
        if response_data.get('count', 0) > 0 and any(num.get('msisdn') == msisdn for num in response_data.get('numbers', [])): return True, response_data
        else: return False, response_data
    except requests.exceptions.RequestException as e:
        response_data, status_code = _handle_vonage_error(e, f"Verify Ownership {msisdn}")
        return False, response_data
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)

def buy_did(username, password, country, msisdn, target_api_key=None, log_enabled=False, treat_420_as_success=False, verify_on_420=False):
    buy_payload = {'country': country, 'msisdn': msisdn}
    if target_api_key: buy_payload['target_api_key'] = target_api_key
    operation_name = f"Vonage DID Buy ({msisdn})"
    request_details = {"URL": NEXMO_BUY_API_URL, "Method": "POST", "Auth": (username, password), "Payload": buy_payload}
    response_data, status_code = None, None
    try:
        response = requests.post(NEXMO_BUY_API_URL, auth=(username, password), data=buy_payload, headers={'Accept': 'application/json'}, timeout=45)
        response.raise_for_status()
        status_code = response.status_code
        response_data = {"message": "Purchase successful"}
        try: response_data.update(response.json())
        except json.JSONDecodeError: pass
    except requests.exceptions.HTTPError as e:
        api_status_code = e.response.status_code
        if api_status_code == 420 and verify_on_420:
            time.sleep(2)
            is_owned, verification_details = _verify_did_ownership(username, password, msisdn, log_enabled)
            if is_owned:
                status_code = 200
                response_data = {"message": "Purchase verified as successful after initial API response 420.", "verification_details": verification_details}
            else: response_data, status_code = _handle_vonage_error(e, f"Buy DID {msisdn}")
        elif api_status_code == 420 and treat_420_as_success:
            status_code = 200
            response_data = {"message": f"Purchase treated as successful (API returned {api_status_code})."}
            try: response_data.update(e.response.json())
            except json.JSONDecodeError: pass
        else: response_data, status_code = _handle_vonage_error(e, f"Buy DID {msisdn}")
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, f"Buy DID {msisdn}")
    except Exception as e: response_data, status_code = _handle_vonage_error(e, f"Buy DID {msisdn}")
    finally:
        if isinstance(response_data, dict):
            response_data.setdefault('msisdn', msisdn)
            response_data.setdefault('country', country)
        else: response_data = {"data": response_data, "msisdn": msisdn, "country": country}
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code


# --- START: MODIFICATION (Add cancel_did function) ---
def cancel_did(username, password, country, msisdn, log_enabled=False):
    """Cancels (releases) a specific Vonage DID from an account."""
    cancel_payload = {'country': country, 'msisdn': msisdn}
    operation_name = f"Vonage DID Cancel ({msisdn})"
    request_details = {"URL": NEXMO_CANCEL_API_URL, "Method": "POST", "Auth": (username, password), "Payload": cancel_payload}
    response_data, status_code = None, None
    print(f"Cancelling DID: {msisdn} in {country}")

    try:
        response = requests.post(
            NEXMO_CANCEL_API_URL,
            auth=(username, password),
            data=cancel_payload,
            headers={'Accept': 'application/json'},
            timeout=30
        )
        response.raise_for_status() # Raises HTTPError for 4xx/5xx responses

        # A 200 OK response indicates success
        status_code = response.status_code
        print(f"Cancel Success: Released {msisdn}.")
        
        # The success response is often empty or a simple confirmation.
        response_data = {"message": f"DID '{msisdn}' cancelled successfully."}
        try:
            # Try to merge any JSON data from the response if it exists
            response_data.update(response.json())
        except json.JSONDecodeError:
            pass # It's okay if there's no JSON body

    except requests.exceptions.RequestException as e:
        response_data, status_code = _handle_vonage_error(e, f"Cancel DID {msisdn}")
    except Exception as e:
        response_data, status_code = _handle_vonage_error(e, f"Cancel DID {msisdn}")
    finally:
        if isinstance(response_data, dict):
            response_data.setdefault('msisdn', msisdn)
        else:
            response_data = {"data": response_data, "msisdn": msisdn}
        if log_enabled:
            log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
            
    return response_data, status_code
# --- END: MODIFICATION ---


def update_did(username, password, country, msisdn, config, log_enabled=False, treat_420_as_success=False):
    """Updates the configuration of a Vonage DID."""
    update_payload = { 'country': country, 'msisdn': msisdn, **config }
    operation_name = f"Vonage DID Update ({msisdn})"
    request_details = {"URL": NEXMO_UPDATE_API_URL, "Method": "POST", "Auth": (username, password), "Payload": update_payload}
    response_data, status_code = None, None
    try:
        response = requests.post(NEXMO_UPDATE_API_URL, auth=(username, password), data=update_payload, headers={'Accept': 'application/json'}, timeout=30)
        api_status_code = response.status_code
        if api_status_code == 420 and treat_420_as_success:
            status_code = 200
            response_data = {"message": f"Update treated as successful (API returned {api_status_code})."}
            try: response_data.update(response.json())
            except json.JSONDecodeError: pass
        else:
            response.raise_for_status()
            status_code = api_status_code
            response_data = {"message": "Update successful"}
            try: response_data.update(response.json())
            except json.JSONDecodeError: pass
        response_data['msisdn'] = msisdn
        response_data['country'] = country
    except requests.exceptions.RequestException as e:
        response_data, status_code = _handle_vonage_error(e, f"Update DID {msisdn}")
        response_data['msisdn'] = msisdn
    except Exception as e:
        response_data, status_code = _handle_vonage_error(e, f"Update DID {msisdn}")
        response_data['msisdn'] = msisdn
    finally:
        if log_enabled:
            log_request_response(operation_name, request_details, response_data, status_code, account_id=username)
    return response_data, status_code


# --- Subaccount Management Client Functions (Unchanged) ---
def list_subaccounts(primary_api_key, primary_api_secret, log_enabled=False):
    operation_name = f"Vonage List Subaccounts ({primary_api_key})"
    url = f"{VONAGE_ACCOUNTS_API_URL}/{primary_api_key}/subaccounts"
    request_details = {"URL": url, "Method": "GET", "Auth": (primary_api_key, primary_api_secret)}
    response_data, status_code = None, None
    try:
        response = requests.get(url, auth=(primary_api_key, primary_api_secret), headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, operation_name)
    except Exception as e: response_data, status_code = _handle_vonage_error(e, operation_name)
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=primary_api_key)
    return response_data, status_code

def create_subaccount(primary_api_key, primary_api_secret, payload, log_enabled=False):
    operation_name = f"Vonage Create Subaccount under {primary_api_key}"
    url = f"{VONAGE_ACCOUNTS_API_URL}/{primary_api_key}/subaccounts"
    request_details = {"URL": url, "Method": "POST", "Auth": (primary_api_key, primary_api_secret), "Payload": payload}
    response_data, status_code = None, None
    try:
        response = requests.post(url, auth=(primary_api_key, primary_api_secret), json=payload, headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, operation_name)
    except Exception as e: response_data, status_code = _handle_vonage_error(e, operation_name)
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=primary_api_key)
    return response_data, status_code

def update_subaccount(primary_api_key, primary_api_secret, subaccount_key, payload, log_enabled=False):
    operation_name = f"Vonage Update Subaccount ({subaccount_key})"
    url = f"{VONAGE_ACCOUNTS_API_URL}/{primary_api_key}/subaccounts/{subaccount_key}"
    request_details = {"URL": url, "Method": "PATCH", "Auth": (primary_api_key, primary_api_secret), "Payload": payload}
    response_data, status_code = None, None
    try:
        response = requests.patch(url, auth=(primary_api_key, primary_api_secret), json=payload, headers={'Accept': 'application/json'}, timeout=30)
        response.raise_for_status()
        response_data = response.json()
        status_code = response.status_code
    except requests.exceptions.RequestException as e: response_data, status_code = _handle_vonage_error(e, operation_name)
    except Exception as e: response_data, status_code = _handle_vonage_error(e, operation_name)
    finally:
        if log_enabled: log_request_response(operation_name, request_details, response_data, status_code, account_id=primary_api_key)
    return response_data, status_code
# --- END OF FILE vendors/vonage/client.py ---