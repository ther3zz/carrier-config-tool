# --- START OF FILE utils/credentials_manager.py ---

import os
import json
from threading import Lock

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
    """
    (Original function, renamed for clarity)
    Loads all credentials from the JSON file and ensures new fields exist.
    """
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
                # Gracefully handle missing fields for older credentials in the file.
                for name, data in creds.items():
                    data.setdefault('default_voice_callback_type', '')
                    data.setdefault('default_voice_callback_value', '')
                return creds
        except (IOError, json.JSONDecodeError):
            return {}

def _file_save_all_credentials(credentials: dict):
    """(Original function, renamed for clarity)"""
    with file_lock:
        os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(credentials, f, indent=4)


def get_all_credentials():
    """
    Loads all credentials from the configured storage source (file or db).
    """
    if STORAGE_MODE == 'db':
        return db_manager.db_get_all_credentials()
    else: # Default to file
        return _file_get_all_credentials()


def get_credential_names():
    """Returns a sorted list of the friendly names of all stored credentials."""
    creds = get_all_credentials()
    return sorted(list(creds.keys()))


def save_credential(name: str, api_key: str, api_secret: str, master_key: str,
                    voice_callback_type: str = '', voice_callback_value: str = '',
                    original_name: str = None):
    """
    Encrypts and saves a new credential or updates an existing one.

    If api_secret is empty/None, it attempts to preserve the existing secret,
    but only if the name and api_key have not changed. A new secret is
    required if the name or api_key are being changed.
    """
    if not all([name, api_key, master_key]):
        raise ValueError("Name, API Key, and Master Key are all required.")

    if not original_name:
        original_name = name

    all_creds = get_all_credentials()
    existing_cred = all_creds.get(original_name)
    
    encrypted_secret = None
    
    # Condition 1: A new secret is provided. Always use it.
    if api_secret:
        encrypted_secret = encrypt_data(api_secret, master_key)
    
    # Condition 2: No new secret provided, and it's an existing credential.
    elif existing_cred:
        # If the user is trying to change the name or API key, they MUST provide the secret again for security.
        if name != original_name or api_key != existing_cred.get('api_key'):
            raise ValueError("A new API Secret is required when changing the Friendly Name or API Key.")
        # Otherwise, we can safely re-use the old encrypted secret.
        encrypted_secret = existing_cred.get('encrypted_secret')
        
    # Condition 3: No secret provided for a brand new credential. This is an error.
    if not encrypted_secret:
        raise ValueError("An API Secret is required to save a new credential.")

    api_key_hint = f"{api_key[:5]}...{api_key[-4:]}" if len(api_key) > 8 else api_key

    if STORAGE_MODE == 'db':
        # --- START: MODIFICATION (Ensure all arguments are passed) ---
        # Call the db_save_credential function with all required parameters.
        db_manager.db_save_credential(
            name, 
            api_key, 
            encrypted_secret, 
            api_key_hint, 
            voice_callback_type, 
            voice_callback_value
        )
        # --- END: MODIFICATION ---
        if name != original_name:
            db_manager.db_delete_credential(original_name)
    else:
        # File-based logic
        new_entry = {
            'api_key': api_key,
            'encrypted_secret': encrypted_secret,
            'api_key_hint': api_key_hint,
            'default_voice_callback_type': voice_callback_type or '',
            'default_voice_callback_value': voice_callback_value or ''
        }
        
        # If the name has been changed, delete the old entry.
        if name != original_name and original_name in all_creds:
            del all_creds[original_name]
        
        all_creds[name] = new_entry
        _file_save_all_credentials(all_creds)


def delete_credential(name: str) -> bool:
    """Deletes a credential entry by its friendly name from the configured storage."""
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
    """
    Retrieves a credential by name, decrypts its secret, and includes default settings.
    """
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

    return {
        'api_key': credential_data.get('api_key'),
        'api_secret': decrypted_secret,
        'default_voice_callback_type': credential_data.get('default_voice_callback_type', ''),
        'default_voice_callback_value': credential_data.get('default_voice_callback_value', '')
    }


def find_and_decrypt_credential_by_groupid(groupid: str, master_key: str) -> dict:
    """
    Finds a credential by groupid from the database, decrypts it, and includes default settings.
    """
    if STORAGE_MODE != 'db':
        raise ValueError("This function is only available in 'db' credential storage mode.")
    if not master_key:
        raise ValueError("A master key is required to decrypt credentials.")

    credential_data = db_manager.db_find_credential_by_groupid_in_name(groupid)

    if not credential_data:
        raise ValueError(f"No credential found for groupid '{groupid}'.")

    encrypted_secret = credential_data.get('encrypted_secret')
    if not encrypted_secret:
        raise ValueError(f"Credential for groupid '{groupid}' is improperly configured.")

    decrypted_secret = decrypt_data(encrypted_secret, master_key)

    return {
        'api_key': credential_data.get('api_key'),
        'api_secret': decrypted_secret,
        'account_name': credential_data.get('name'),
        'default_voice_callback_type': credential_data.get('default_voice_callback_type'),
        'default_voice_callback_value': credential_data.get('default_voice_callback_value')
    }

# --- END OF FILE utils/credentials_manager.py ---