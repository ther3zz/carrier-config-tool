# --- START OF FILE utils/config_loader.py ---
import os
import json

def load_config_file(filepath):
    """Loads a JSON configuration file.

    Creates the directory and an empty list file if it doesn't exist.
    Returns an empty list if the file is found but cannot be decoded.
    """
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Configuration file {filepath} not found. Creating empty default.")
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump([], f)
        except OSError as e:
            print(f"Error: Could not create directory or file {filepath}: {e}")
        return []
    except json.JSONDecodeError:
        print(f"Warning: Error decoding JSON from {filepath}. Returning empty list.")
        return []
    except Exception as e:
        print(f"An unexpected error occurred loading {filepath}: {e}")
        return []

# --- END OF FILE utils/config_loader.py ---