import os
from datetime import date, datetime
from typing import List, Optional
from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
)
from models import Activity

class GarminClient:
    def __init__(self, email: str, password: str, token_path: str = "~/.garminconnect"):
        self.email = email
        self.password = password
        self.token_path = os.path.expanduser(token_path)
        self.client = None
        
        try:
            # First attempt: Try to restore session from existing tokens.
            # This is key to avoiding Cloudflare blocks that happen with repeated logins.
            print(f"Attempting to restore Garmin session from: {self.token_path}")
            # Initialize with minimal params to trigger token restoration in login()
            self.client = Garmin()
            self.client.login(self.token_path)
        except (FileNotFoundError, GarminConnectAuthenticationError, GarminConnectTooManyRequestsError, Exception) as e:
            # Second attempt: Fresh login with credentials
            print(f"Token restoration failed: {e}. Falling back to fresh login with credentials...")
            try:
                self.client = Garmin(
                    email=self.email,
                    password=self.password,
                    prompt_mfa=self.get_mfa
                )
                self.client.login(self.token_path)
            except Exception as e:
                print(f"Failed to authenticate with Garmin: {e}")
                raise e

    def get_mfa(self):
        # This will trigger an interactive input in the terminal if Garmin requires MFA.
        return input("MFA one-time code: ").strip()

    def get_activities(self, oldest: date, newest: date) -> List[Activity]:
        # Fetch summary data. Garmin Connect typically gives a list of recent activities.
        raw_activities = self.client.get_activities(0, 50)
        
        activities = []
        for item in raw_activities:
            # startTimeLocal is string like "2026-04-08 10:30:00"
            start_time = datetime.fromisoformat(item["startTimeLocal"])
            if oldest <= start_time.date() <= newest:
                activities.append(Activity(
                    platform_id=str(item.get("activityId")),
                    name=item.get("activityName", "Unknown Activity"),
                    start_time=start_time,
                    duration_sec=int(item.get("duration", 0)),
                    type=item.get("activityType", {}).get("typeKey", "Unknown")
                ))
        return activities

    def update_activity(self, activity_id: str, name: str, description: Optional[str] = None):
        self.client.update_activity(activity_id, activity_name=name, description=description)
