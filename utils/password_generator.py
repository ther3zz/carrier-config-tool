# --- START OF FILE utils/password_generator.py ---
import secrets
import string

def generate_secure_secret(length=16):
    """
    Generates a cryptographically secure random string suitable for API secrets.
    Ensures compliance with common requirements (like Vonage's):
    - Minimum length (default 16)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    alphabet = string.ascii_letters + string.digits
    
    while True:
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        
        # Verify complexity requirements
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)):
            return password
# --- END OF FILE utils/password_generator.py ---