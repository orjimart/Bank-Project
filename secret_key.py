# secret_key.py
import os

# Generate a 24-byte secret key
secret_key = os.urandom(24).hex()

# Print the secret key
print("Generated Secret Key:", secret_key)
