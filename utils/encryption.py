import os
import base64
import secrets # Using the 'secrets' module for cryptographic randomness
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# This file will store a random salt for the key derivation function.
# The path can be overridden by an environment variable for deployment flexibility.
SALT_FILE = os.environ.get('CREDENTIAL_SALT_PATH', os.path.join('config', 'salt.bin'))

def get_or_create_salt():
    """
    Retrieves the salt from the salt file, or creates and saves a new one if it doesn't exist.
    This ensures that the key derivation is consistent for a given installation.
    """
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, 'rb') as f:
            salt = f.read()
    else:
        # Ensure the config directory exists before trying to write the file
        os.makedirs(os.path.dirname(SALT_FILE), exist_ok=True)
        # Generate a new cryptographically secure random salt using the secrets module
        salt = secrets.token_bytes(16)
        with open(SALT_FILE, 'wb') as f:
            f.write(salt)
    return salt

def get_key_from_master(master_key: str) -> bytes:
    """
    Derives a 32-byte key suitable for Fernet encryption from a user-provided master key string.
    Uses PBKDF2HMAC to make the derived key resistant to brute-force attacks.

    Args:
        master_key: The user-provided string to be used as the master key.

    Returns:
        A URL-safe, base64-encoded 32-byte key.
    
    Raises:
        ValueError: If the master key is not a non-empty string.
    """
    if not isinstance(master_key, str) or not master_key:
        raise ValueError("Master key must be a non-empty string.")
        
    salt = get_or_create_salt()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,  # A modern, recommended number of iterations (as of 2023/2024)
        backend=default_backend()
    )
    # The derived key needs to be base64-encoded to be used by Fernet
    key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
    return key

def encrypt_data(data: str, master_key: str) -> str:
    """
    Encrypts a string using the key derived from the master key.

    Args:
        data: The plaintext string to encrypt.
        master_key: The master key to use for deriving the encryption key.

    Returns:
        A URL-safe, base64-encoded, encrypted string.
    
    Raises:
        ValueError: If the data to encrypt is not a non-empty string.
    """
    if not isinstance(data, str) or not data:
        raise ValueError("Data to encrypt must be a non-empty string.")

    key = get_key_from_master(master_key)
    fernet = Fernet(key)
    encrypted_data = fernet.encrypt(data.encode())
    return encrypted_data.decode()

def decrypt_data(encrypted_data: str, master_key: str) -> str:
    """
    Decrypts a string using the key derived from the master key.

    Args:
        encrypted_data: The encrypted, base64-encoded string.
        master_key: The master key used during encryption.

    Returns:
        The original plaintext string.
    
    Raises:
        ValueError: If decryption fails, which can happen if the master key is wrong,
                    the data is corrupted, or the token has expired (not applicable here).
    """
    if not isinstance(encrypted_data, str) or not encrypted_data:
        raise ValueError("Encrypted data must be a non-empty string.")
        
    try:
        key = get_key_from_master(master_key)
        fernet = Fernet(key)
        decrypted_data = fernet.decrypt(encrypted_data.encode())
        return decrypted_data.decode()
    except Exception as e:
        # Fernet can raise various exceptions for invalid tokens, padding errors, etc.
        # We catch the generic exception to avoid leaking implementation details and
        # raise a single, consistent error to the caller.
        # For debugging, the original error `e` can be logged here.
        raise ValueError("Decryption failed. The master key may be incorrect or the data is corrupted.")