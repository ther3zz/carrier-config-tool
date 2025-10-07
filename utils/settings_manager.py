# --- START OF FILE utils/settings_manager.py ---

from . import db_manager

# Define the hardcoded default values for all application settings.
# This ensures the application can always run, even with an empty database.
DEFAULT_SETTINGS = {
    'max_concurrent_requests': 5,
    'delay_between_batches_ms': 1000,
    'store_logs_enabled': False,
    'treat_420_as_success_buy': False,
    'verify_on_420_buy': False,
    'treat_420_as_success_configure': False
}

# A simple in-memory cache to avoid hitting the database on every request.
_settings_cache = None

def get_all_settings() -> dict:
    """
    Fetches all settings from the database and merges them with the defaults.
    The database values override the defaults. Caches the result.
    """
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache

    # Start with a copy of the defaults.
    settings = DEFAULT_SETTINGS.copy()
    
    # Fetch settings from the database.
    db_settings = db_manager.db_get_all_settings()

    # Update the defaults with any values found in the database.
    # This also handles type conversion from the string values stored in the DB.
    for key, value in db_settings.items():
        if key in settings:
            default_type = type(DEFAULT_SETTINGS.get(key))
            try:
                if default_type == bool:
                    settings[key] = value.lower() in ['true', '1', 't']
                else:
                    settings[key] = default_type(value)
            except (ValueError, TypeError):
                # If conversion fails, stick with the default value.
                print(f"Warning: Could not convert setting '{key}' with value '{value}' to {default_type}. Using default.")
    
    _settings_cache = settings
    return _settings_cache

def save_settings(new_settings: dict):
    """
    Saves a dictionary of settings to the database.
    """
    global _settings_cache
    for key, value in new_settings.items():
        # Ensure the setting is one we know about to prevent saving arbitrary data.
        if key in DEFAULT_SETTINGS:
            # Convert all values to string for database storage.
            db_manager.db_save_setting(key, str(value))
    
    # Invalidate the cache. The next call to get_all_settings will reload from the DB.
    _settings_cache = None
    print("Settings saved successfully. Cache invalidated.")

def get_setting(key: str):
    """
    Convenience function to get a single setting's value.
    """
    return get_all_settings().get(key)

# --- END OF FILE utils/settings_manager.py ---