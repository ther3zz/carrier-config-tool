# --- START OF FILE utils/encryption.py ---

import os
import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# --- START: MODIFICATION (Read Salt from Environment) ---

# Instead of a file, we now require the salt as an environment variable for stateless deployments.
SALT_FROM_ENV = os.environ.get('ENCRYPTION_SALT')
if not SALT_FROM_ENV:
    raise RuntimeError("CRITICAL: ENCRYPTION_SALT environment variable not set. Please generate a salt and add it to your .env file.")

# The salt needs to be in bytes.
SALT = SALT_FROM_ENV.encode()

# --- END: MODIFICATION ---


def get_key_from_master(master_key: str) -> bytes:
    """
    Derives a cryptographically strong key from the user-provided master key and the application's salt.
    """
    if not master_key:
        raise ValueError("A master key is required.")
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=480000, # Increased iterations for better security
    )
    key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
    return key


def encrypt_data(data: str, master_key: str) -> str:
    """
    Encrypts a string using a key derived from the master key.
    """
    if not data:
        raise ValueError("Data to encrypt cannot be empty.")
    
    key = get_key_from_master(master_key)
    f = Fernet(key)
    encrypted_data = f.encrypt(data.encode())
    return encrypted_data.decode()


def decrypt_data(encrypted_data: str, master_key: str) -> str:
    """
    Decrypts a string using a key derived from the master key.
    Raises ValueError on failure.
    """
    if not encrypted_data:
        raise ValueError("Encrypted data cannot be empty.")
        
    key = get_key_from_master(master_key)
    f = Fernet(key)
    try:
        decrypted_data = f.decrypt(encrypted_data.encode())
        return decrypted_data.decode()
    except InvalidToken:
        # This is a generic but clear error. The failure could be due to a wrong master key,
        # a wrong salt (if it was changed), or corrupted data.
        raise ValueError("Decryption failed. The master key may be incorrect or the data is corrupted.")
    except Exception as e:
        # Catch any other potential crypto errors
        raise ValueError(f"An unexpected decryption error occurred: {e}")

# --- We no longer need the file-based salt functions, so they have been removed. ---

# --- END OF FILE utils/encryption.py ---