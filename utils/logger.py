# --- START OF FILE utils/logger.py ---

import os
import logging
from logging.handlers import RotatingFileHandler
import json
import copy # Import the copy module for deep copying request details
from fastapi import Request # Import for type hinting

def setup_logging():
    """
    Configures a basic root logger for general application events (e.g., startup).
    This will log to the console and a general 'system.log' file.
    API request/response logging is handled separately.
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    root_logger = logging.getLogger()
    
    if not root_logger.hasHandlers():
        root_logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # General system log handler
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'system.log'), 
            maxBytes=1024 * 1024 * 2,  # 2 MB
            backupCount=3
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        root_logger.info("System logging configured.")

def _get_account_logger(account_id: str) -> logging.Logger:
    """
    Gets a specific logger for a given account_id.
    If the logger doesn't have a file handler, it creates one.
    This ensures each account logs to its own file.
    """
    log_dir = 'logs'
    # Sanitize account_id to be a valid filename
    safe_filename = "".join([c for c in account_id if c.isalnum()]) + ".log"
    log_path = os.path.join(log_dir, safe_filename)

    logger = logging.getLogger(account_id)
    
    # If this is the first time we're getting this logger, configure its handler
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        # Prevent logs from propagating up to the root logger to avoid duplicates
        logger.propagate = False 
        
        handler = RotatingFileHandler(log_path, maxBytes=1024 * 1024 * 5, backupCount=5)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

# --- START: MODIFICATION ---
def _obfuscate_payload(payload: dict) -> dict:
    """
    Takes a payload dictionary, deep copies it, and obfuscates common sensitive keys.
    """
    loggable_payload = copy.deepcopy(payload)
    sensitive_keys = ['master_key', 'api_key', 'api_secret', 'secret', 'password', 'old_master_key', 'new_master_key']

    for key, value in loggable_payload.items():
        if key in sensitive_keys and isinstance(value, str) and value:
            loggable_payload[key] = f"***{value[-4:]}" if len(value) > 4 else "***"
    
    return loggable_payload
# --- END: MODIFICATION ---

def _obfuscate_credentials(request_details: dict) -> dict:
    """
    Takes a request details dictionary, deep copies it, and obfuscates credentials.
    """
    # Create a deep copy to avoid modifying the original object
    loggable_details = copy.deepcopy(request_details)

    if "Auth" in loggable_details and isinstance(loggable_details["Auth"], (list, tuple)) and len(loggable_details["Auth"]) == 2:
        key, secret = loggable_details["Auth"]
        # Obfuscate the secret
        obfuscated_secret = f"***{secret[-4:]}" if len(secret) > 4 else "***"
        loggable_details["Auth"] = (key, obfuscated_secret)

    # Also check for plaintext 'password' or 'api_secret' in payload
    if "Payload" in loggable_details and isinstance(loggable_details["Payload"], dict):
        for key in ['password', 'api_secret', 'secret']:
            if key in loggable_details["Payload"]:
                secret = loggable_details["Payload"][key]
                loggable_details["Payload"][key] = f"***{secret[-4:]}" if len(secret) > 4 else "***"

    return loggable_details

# --- START: MODIFICATION ---
def log_incoming_request(request: Request, payload: dict):
    """
    Logs an incoming FastAPI request to the main system log.
    """
    try:
        system_logger = logging.getLogger() # Get the root logger
        
        log_entry = {
            "event_type": "IncomingFastAPIRequest",
            "client_ip": request.client.host,
            "method": request.method,
            "path": request.url.path,
            "payload": _obfuscate_payload(payload)
        }
        system_logger.info(json.dumps(log_entry))
    except Exception as e:
        system_logger = logging.getLogger("system")
        system_logger.error(f"Failed to write incoming request log: {e}")
# --- END: MODIFICATION ---

def log_request_response(operation_name, request_details, response_data, status_code, account_id):
    """
    Logs an API request and response to a file specific to the account_id,
    with credentials obfuscated.
    """
    if not account_id:
        logging.getLogger("system").error("log_request_response called without an account_id.")
        return

    try:
        logger = _get_account_logger(account_id)
        
        # Obfuscate credentials before logging
        loggable_request = _obfuscate_credentials(request_details)

        log_entry = {
            "operation": operation_name,
            "status_code": status_code,
            "request": loggable_request,
            "response": response_data
        }
        logger.info(json.dumps(log_entry, indent=2))
    except Exception as e:
        # Log failure to the general system logger
        system_logger = logging.getLogger("system")
        system_logger.error(f"Failed to write API log for account '{account_id}': {e}")


def clear_logs():
    """Clears all .log files from the logs directory."""
    log_dir = 'logs'
    try:
        if os.path.isdir(log_dir):
            for filename in os.listdir(log_dir):
                if filename.endswith(".log"):
                    os.remove(os.path.join(log_dir, filename))
            logging.getLogger("system").info("All log files cleared.")
            return True
        return False
    except Exception as e:
        logging.getLogger("system").error(f"Error clearing log files: {e}")
        return False

# --- END OF FILE utils/logger.py ---