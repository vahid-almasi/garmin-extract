import argparse
from pathlib import Path

from garminconnect import Garmin

from garmin_extract.credentials import get_credentials, reset_credentials
from garmin_extract.sync import sync

ACTIVITIES_DIR = Path(__file__).parent.parent / "activities"


def main():
    parser = argparse.ArgumentParser(
        description="Sync Garmin Connect activities to local storage."
    )
    parser.add_argument(
        "--reset-credentials",
        action="store_true",
        help="Clear saved Garmin credentials from the OS keyring and exit.",
    )
    args = parser.parse_args()

    if args.reset_credentials:
        reset_credentials()
        return

    email, password = get_credentials()

    client = Garmin(
        email,
        password,
        prompt_mfa=lambda: input("Enter MFA code: "),
    )
    client.login(str(Path.home() / ".garminconnect"))

    synced = sync(client, ACTIVITIES_DIR)

    print(f"Synced {len(synced)} new activities: {synced}")
