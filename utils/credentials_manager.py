# --- START OF FILE utils/credentials_manager.py ---

import os
import json
from threading import Lock
import logging

# Import the encryption functions from our new utility
from .encryption import encrypt_data, decrypt_data

# Import the new database manager
from . import db_manager

# Determine the storage mode from an environment variable. Default to 'file'.
STORAGE_MODE = os.environ.get('CREDENTIAL_STORAGE_MODE', 'file').lower()


# Define the path to the file where encrypted credentials will be stored.
CREDENTIALS_FILE = os.path.join('config', 'credentials.json')

# A file lock to prevent race conditions when reading/writing the JSON file.
file_lock = Lock()


# Initialize the database if the mode is 'db'.
if STORAGE_MODE == 'db':
    db_manager.init_db()


def _file_get_all_credentials():
    # (Function unchanged)
    with file_lock:
        if not os.path.exists(CREDENTIALS_FILE):
            return {}
        try:
            os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
            with open(CREDENTIALS_FILE, 'r') as f:
                content = f.read()
                if not content:
                    return {}
                creds = json.loads(content)
                for name, data in creds.items():
                    data.setdefault('default_voice_callback_type', '')
                    data.setdefault('default_voice_callback_value', '')
                return creds
        except (IOError, json.JSONDecodeError):
            return {}

def _file_save_all_credentials(credentials: dict):
    # (Function unchanged)
    with file_lock:
        os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(credentials, f, indent=4)


def get_all_credentials():
    # (Function unchanged)
    if STORAGE_MODE == 'db':
        return db_manager.db_get_all_credentials()
    else: # Default to file
        return _file_get_all_credentials()


def get_credential_names():
    # (Function unchanged)
    creds = get_all_credentials()
    return sorted(list(creds.keys()))


def save_credential(name: str, api_key: str, api_secret: str, master_key: str,
                    voice_callback_type: str = '', voice_callback_value: str = '',
                    original_name: str = None):
    # (Function unchanged)
    if not all([name, api_key, master_key]):
        raise ValueError("Name, API Key, and Master Key are all required.")
    if not original_name:
        original_name = name
    all_creds = get_all_credentials()
    existing_cred = all_creds.get(original_name)
    encrypted_secret = None
    if api_secret:
        encrypted_secret = encrypt_data(api_secret, master_key)
    elif existing_cred:
        if name != original_name or api_key != existing_cred.get('api_key'):
            raise ValueError("A new API Secret is required when changing the Friendly Name or API Key.")
        encrypted_secret = existing_cred.get('encrypted_secret')
    if not encrypted_secret:
        raise ValueError("An API Secret is required to save a new credential.")
    api_key_hint = f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 8 else api_key
    if STORAGE_MODE == 'db':
        db_manager.db_save_credential(name, api_key, encrypted_secret, api_key_hint, voice_callback_type, voice_callback_value)
        if name != original_name:
            db_manager.db_delete_credential(original_name)
    else:
        new_entry = { 'api_key': api_key, 'encrypted_secret': encrypted_secret, 'api_key_hint': api_key_hint, 'default_voice_callback_type': voice_callback_type or '', 'default_voice_callback_value': voice_callback_value or '' }
        if name != original_name and original_name in all_creds:
            del all_creds[original_name]
        all_creds[name] = new_entry
        _file_save_all_credentials(all_creds)


def delete_credential(name: str) -> bool:
    # (Function unchanged)
    if STORAGE_MODE == 'db':
        return db_manager.db_delete_credential(name)
    else:
        all_creds = _file_get_all_credentials()
        if name in all_creds:
            del all_creds[name]
            _file_save_all_credentials(all_creds)
            return True
        return False


def get_decrypted_credentials(name: str, master_key: str) -> dict:
    # (Function unchanged)
    if not master_key:
        raise ValueError("A master key is required to decrypt credentials.")
    all_creds = get_all_credentials()
    credential_data = all_creds.get(name)
    if not credential_data:
        raise ValueError(f"Credential '{name}' not found.")
    encrypted_secret = credential_data.get('encrypted_secret')
    if not encrypted_secret:
         raise ValueError(f"Credential '{name}' is improperly configured (missing encrypted_secret).")
    decrypted_secret = decrypt_data(encrypted_secret, master_key)
    return { 'api_key': credential_data.get('api_key'), 'api_secret': decrypted_secret, 'default_voice_callback_type': credential_data.get('default_voice_callback_type', ''), 'default_voice_callback_value': credential_data.get('default_voice_callback_value', '') }


def find_and_decrypt_credential_by_groupid(groupid: str, master_key: str) -> dict:
    # (Function unchanged, including debug logs)
    log = logging.getLogger("system")
    if STORAGE_MODE != 'db':
        log.error("find_and_decrypt_credential_by_groupid called while not in 'db' mode.")
        raise ValueError("This function is only available in 'db' credential storage mode.")
    if not master_key:
        log.error("find_and_decrypt_credential_by_groupid called without a master key.")
        raise ValueError("A master key is required to decrypt credentials.")
    log.info(f"Attempting to find credential in DB for groupid: '{groupid}'")
    credential_data = db_manager.db_find_credential_by_groupid_in_name(groupid)
    if not credential_data:
        log.warning(f"DB search returned NO results for groupid: '{groupid}'")
        raise ValueError(f"No credential found for groupid '{groupid}'.")
    log.info(f"DB search SUCCESS for groupid '{groupid}'. Found account: '{credential_data.get('name')}'")
    encrypted_secret = credential_data.get('encrypted_secret')
    if not encrypted_secret:
        log.error(f"Credential '{credential_data.get('name')}' is missing its encrypted_secret.")
        raise ValueError(f"Credential for groupid '{groupid}' is improperly configured.")
    log.info(f"Found encrypted secret snippet: ...{encrypted_secret[-10:]}")
    log.info("Attempting to decrypt secret...")
    try:
        decrypted_secret = decrypt_data(encrypted_secret, master_key)
        log.info("Decryption SUCCESSFUL.")
    except ValueError as e:
        log.error(f"DECRYPTION FAILED for account '{credential_data.get('name')}'. This almost always means the MASTER_KEY is incorrect. Error: {e}")
        raise ValueError(f"Decryption failed for groupid '{groupid}'. The master key may be incorrect.")
    return { 'api_key': credential_data.get('api_key'), 'api_secret': decrypted_secret, 'account_name': credential_data.get('name'), 'default_voice_callback_type': credential_data.get('default_voice_callback_type'), 'default_voice_callback_value': credential_data.get('default_voice_callback_value') }

# --- START: MODIFICATION (Add Re-Keying Logic) ---
def rekey_all_credentials(old_master_key: str, new_master_key: str) -> dict:
    """
    Iterates through all credentials, decrypts them with the old key,
    and re-encrypts them with the new key.
    """
    all_creds = get_all_credentials()
    results = {"success": [], "failed": []}
    updated_creds = {}

    if not all_creds:
        return results

    for name, data in all_creds.items():
        try:
            # Step 1: Decrypt with the old key
            encrypted_secret = data.get('encrypted_secret')
            if not encrypted_secret:
                raise ValueError("Missing encrypted_secret field.")
            
            decrypted_secret = decrypt_data(encrypted_secret, old_master_key)

            # Step 2: Re-encrypt with the new key
            new_encrypted_secret = encrypt_data(decrypted_secret, new_master_key)
            
            # Prepare the updated entry
            updated_data = data.copy()
            updated_data['encrypted_secret'] = new_encrypted_secret
            updated_creds[name] = updated_data
            
            results['success'].append(name)
        except Exception as e:
            results['failed'].append({"name": name, "reason": str(e)})

    # Step 3: If there were failures, do NOT save anything to prevent data corruption.
    if results['failed']:
        # The calling function in app.py will see the 'failed' list and return an error.
        return results

    # Step 4: If all were successful, atomically save the updated credentials.
    if STORAGE_MODE == 'db':
        # For DB, we iterate and save each one individually.
        for name, data in updated_creds.items():
             db_manager.db_save_credential(
                name, 
                data['api_key'], 
                data['encrypted_secret'], 
                data['api_key_hint'],
                data.get('default_voice_callback_type', ''),
                data.get('default_voice_callback_value', '')
            )
    else:
        # For file, we overwrite the entire file with the re-encrypted data.
        _file_save_all_credentials(updated_creds)
        
    return results
# --- END: MODIFICATION ---

# --- END OF FILE utils/credentials_manager.py ---
