import os

from garminconnect import Garmin

client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
client.login()
activities = client.get_activities(0, 10)  # last 10
print(activities)