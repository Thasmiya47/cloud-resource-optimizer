import os
from pathlib import Path

from cryptography.fernet import Fernet, MultiFernet
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

current_key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
previous_key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY_PREVIOUS")

if not current_key:
    raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is missing from .env")

keys = [Fernet(current_key.encode("utf-8"))]

if previous_key:
    keys.append(Fernet(previous_key.encode("utf-8")))

cipher = MultiFernet(keys)


def encrypt_secret(secret):
    return cipher.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_secret):
    return cipher.decrypt(
        encrypted_secret.encode("utf-8")
    ).decode("utf-8")