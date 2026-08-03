import os
from pathlib import Path

from garminconnect import Garmin

from garmin_sync import sync

ACTIVITIES_DIR = Path(__file__).parent / "activities"


def main():
    client = Garmin(
        os.environ["GARMIN_EMAIL"],
        os.environ["GARMIN_PASSWORD"],
        prompt_mfa=lambda: input("Enter MFA code: "),
    )
    client.login(str(Path.home() / ".garminconnect"))

    synced = sync(client, ACTIVITIES_DIR)

    print(f"Synced {len(synced)} new activities: {synced}")


if __name__ == "__main__":
    main()