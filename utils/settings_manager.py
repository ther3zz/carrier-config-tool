# --- START OF FILE utils/settings_manager.py ---

import os
from threading import Lock
from . import db_manager

# --- START: MODIFICATION (Add Granular Notification Toggles) ---
DEFAULT_SETTINGS = {
    'max_concurrent_requests': '5',
    'delay_between_batches_ms': '1000',
    'store_logs_enabled': 'False',
    'treat_420_as_success_buy': 'False',
    'verify_on_420_buy': 'False',
    'treat_420_as_success_configure': 'False',
    'notifications_enabled': 'False', # Master switch
    'notifications_webhook_url': '',
    'notifications_secret': '',
    'notifications_content_type': 'application/json',
    'notifications_on_subaccount_created': 'False', # Granular switch
    'notifications_on_did_provisioned': 'False',   # Granular switch
    'notifications_on_did_released': 'False'       # Granular switch
}
# --- END: MODIFICATION ---

# A simple in-memory cache for settings to reduce DB calls.
settings_cache = {}
cache_lock = Lock()
STORAGE_MODE = os.environ.get('CREDENTIAL_STORAGE_MODE', 'file').lower()

def get_all_settings():
    """
    Loads all settings from the database, falling back to defaults
    for any that are missing. This populates the cache.
    """
    with cache_lock:
        global settings_cache
        if STORAGE_MODE == 'db':
            db_settings = db_manager.db_get_all_settings()
            settings_cache = {**DEFAULT_SETTINGS, **db_settings}
        else:
            settings_cache = DEFAULT_SETTINGS.copy()
        return settings_cache

def get_setting(key, default=None):
    """
    Retrieves a single setting value by key, using the cache.
    Populates the cache on first run.
    """
    with cache_lock:
        if not settings_cache:
            get_all_settings() 
        
        value_str = settings_cache.get(key)
        
        if isinstance(value_str, str):
            if value_str.lower() == 'true':
                return True
            if value_str.lower() == 'false':
                return False
        
        return value_str if value_str is not None else default

def save_settings(new_settings: dict):
    """
    Saves a dictionary of settings to the database and updates the cache.
    """
    if STORAGE_MODE != 'db':
        return

    with cache_lock:
        global settings_cache
        for key, value in new_settings.items():
            if key in DEFAULT_SETTINGS:
                str_value = str(value)
                db_manager.db_save_setting(key, str_value)
                settings_cache[key] = str_value
            else:
                print(f"Warning: Attempted to save unknown setting '{key}'. Ignoring.")

# Initialize the cache on startup
get_all_settings()
# --- END OF FILE utils/settings_manager.py ---