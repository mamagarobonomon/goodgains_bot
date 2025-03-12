from cryptography.fernet import Fernet

# Generate a Fernet key
key = Fernet.generate_key()
print(f"Generated key: {key.decode()}")

# You can then use this key to encrypt your wallet private key
# For example:
private_key = "04646781e11d383e694b3679c0b489890235accfc4aa76737988711b2ae753a2"  # Replace with your actual private key
f = Fernet(key)
encrypted_key = f.encrypt(private_key.encode())
print(f"Encrypted private key: {encrypted_key.decode()}")

# Save both the ENCRYPTION_KEY and ENCRYPTED_WALLET_PRIVATE_KEY to your .env file