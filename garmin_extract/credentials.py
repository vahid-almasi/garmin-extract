import getpass
import os

import keyring
from keyring.errors import KeyringError

KEYRING_SERVICE = "garmin-extract"
KEYRING_EMAIL_KEY = "email"


def _keyring_get(username):
    try:
        return keyring.get_password(KEYRING_SERVICE, username)
    except KeyringError:
        return None


def _keyring_set(username, value):
    try:
        keyring.set_password(KEYRING_SERVICE, username, value)
    except KeyringError:
        print("Warning: no OS keyring available; credentials will not be saved for next run.")


def get_credentials():
    env_email = os.environ.get("GARMIN_EMAIL")
    env_password = os.environ.get("GARMIN_PASSWORD")
    if env_email and env_password:
        return env_email, env_password

    stored_email = _keyring_get(KEYRING_EMAIL_KEY)
    stored_password = _keyring_get(stored_email) if stored_email else None
    if stored_email and stored_password:
        return stored_email, stored_password

    email = input("Garmin email: ")
    password = getpass.getpass("Garmin password: ")
    _keyring_set(KEYRING_EMAIL_KEY, email)
    _keyring_set(email, password)
    return email, password


def reset_credentials():
    stored_email = _keyring_get(KEYRING_EMAIL_KEY)
    if not stored_email:
        print("No stored credentials found.")
        return

    for username in (stored_email, KEYRING_EMAIL_KEY):
        try:
            keyring.delete_password(KEYRING_SERVICE, username)
        except KeyringError:
            pass
    print("Stored credentials cleared.")
