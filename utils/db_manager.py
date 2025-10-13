# --- START OF FILE utils/db_manager.py ---

import os
import mariadb
import json
from threading import Lock

# A lock to ensure thread safety for database operations, especially for initialization.
db_lock = Lock()
is_db_initialized = False

def get_db_connection():
    """
    Establishes a connection to the MariaDB database using environment variables.
    """
    try:
        conn = mariadb.connect(
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 3306)),
            database=os.environ.get("DB_NAME")
        )
        return conn
    except mariadb.Error as e:
        print(f"Error connecting to MariaDB Platform: {e}")
        raise e

def init_db():
    """
    Initializes the database by creating/updating tables for credentials and settings.
    This function is thread-safe.
    """
    global is_db_initialized
    with db_lock:
        if is_db_initialized:
            return

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # --- Credentials Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    api_key VARCHAR(255) NOT NULL,
                    encrypted_secret TEXT NOT NULL,
                    api_key_hint VARCHAR(50)
                )
            """)
            cursor.execute("""
                ALTER TABLE credentials
                ADD COLUMN IF NOT EXISTS default_voice_callback_type VARCHAR(255),
                ADD COLUMN IF NOT EXISTS default_voice_callback_value VARCHAR(255)
            """)
            
            # --- START: MODIFICATION (Add App Settings Table) ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    setting_key VARCHAR(255) UNIQUE NOT NULL,
                    setting_value TEXT
                )
            """)
            # --- END: MODIFICATION ---

            conn.commit()
            print("Database initialized successfully. Tables are up to date.")
            is_db_initialized = True
        except mariadb.Error as e:
            print(f"Error initializing database: {e}")
        finally:
            if conn:
                conn.close()

# --- START: MODIFICATION (New Functions for App Settings) ---

def db_get_all_settings() -> dict:
    """Loads all key-value settings from the app_settings table."""
    conn = None
    settings = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT setting_key, setting_value FROM app_settings")
        for row in cursor:
            settings[row['setting_key']] = row['setting_value']
        return settings
    except mariadb.Error as e:
        print(f"Error fetching all app settings from DB: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def db_save_setting(key: str, value: str):
    """Saves or updates a single setting in the app_settings table (upsert)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO app_settings (setting_key, setting_value)
            VALUES (?, ?)
            ON DUPLICATE KEY UPDATE
                setting_value = VALUES(setting_value)
        """
        cursor.execute(query, (key, str(value) if value is not None else None))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error saving setting '{key}' to DB: {e}")
        raise ValueError(f"Failed to save setting '{key}' to the database.") from e
    finally:
        if conn:
            conn.close()

# --- END: MODIFICATION ---


# --- Credential Management Functions (Unchanged) ---

def db_get_all_credentials():
    """Loads all credentials from the database, including new default settings."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name, api_key, encrypted_secret, api_key_hint, default_voice_callback_type, default_voice_callback_value FROM credentials")
        
        credentials_from_db = cursor.fetchall()
        
        credentials_dict = {
            cred['name']: {
                'api_key': cred['api_key'],
                'encrypted_secret': cred['encrypted_secret'],
                'api_key_hint': cred['api_key_hint'],
                'default_voice_callback_type': cred['default_voice_callback_type'],
                'default_voice_callback_value': cred['default_voice_callback_value']
            } for cred in credentials_from_db
        }
        return credentials_dict
    except mariadb.Error as e:
        print(f"Error fetching all credentials from DB: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def db_save_credential(name: str, api_key: str, encrypted_secret: str, api_key_hint: str, voice_callback_type: str, voice_callback_value: str):
    """Saves or updates a credential in the database, including the new default settings."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO credentials (name, api_key, encrypted_secret, api_key_hint, default_voice_callback_type, default_voice_callback_value)
            VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                api_key = VALUES(api_key),
                encrypted_secret = VALUES(encrypted_secret),
                api_key_hint = VALUES(api_key_hint),
                default_voice_callback_type = VALUES(default_voice_callback_type),
                default_voice_callback_value = VALUES(default_voice_callback_value)
        """
        cursor.execute(query, (name, api_key, encrypted_secret, api_key_hint, voice_callback_type or '', voice_callback_value or ''))
        conn.commit()
    except mariadb.Error as e:
        print(f"Error saving credential '{name}' to DB: {e}")
        raise ValueError(f"Failed to save credential '{name}' to the database.") from e
    finally:
        if conn:
            conn.close()

def db_delete_credential(name: str) -> bool:
    """Deletes a credential from the database by its name."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM credentials WHERE name = ?", (name,))
        conn.commit()
        return cursor.rowcount > 0
    except mariadb.Error as e:
        print(f"Error deleting credential '{name}' from DB: {e}")
        return False
    finally:
        if conn:
            conn.close()

def db_find_credential_by_groupid_in_name(groupid: str):
    """
    Finds a credential by its groupid within the credential name.
    - If the groupid is less than 3 characters, it performs a whole-word search to avoid partial matches (e.g., '1' matching '10').
    - Otherwise, it performs a broad substring search for backward compatibility.
    """
    conn = None
    if not groupid:
        return None
        
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # --- START: MODIFICATION ---
        if len(groupid) < 3:
            # Use REGEXP for a "whole word" search to find the exact number.
            # This prevents '1' from matching '10', '11', etc. in names like "GroupId [10]".
            # '[[:<:]]' and '[[:>:]]' are word boundaries in MariaDB/MySQL REGEXP.
            query = "SELECT name, api_key, encrypted_secret, default_voice_callback_type, default_voice_callback_value FROM credentials WHERE name REGEXP ?"
            search_pattern = f"[[:<:]]{groupid}[[:>:]]"
        else:
            # For longer, more unique groupids, the original substring search is acceptable.
            query = "SELECT name, api_key, encrypted_secret, default_voice_callback_type, default_voice_callback_value FROM credentials WHERE name LIKE ?"
            search_pattern = f"%{groupid}%"
        # --- END: MODIFICATION ---

        cursor.execute(query, (search_pattern,))
        result = cursor.fetchone()
        return result
    except mariadb.Error as e:
        print(f"Error finding credential by groupid '{groupid}' in name: {e}")
        return None
    finally:
        if conn:
            conn.close()
# --- END OF FILE utils/db_manager.py ---