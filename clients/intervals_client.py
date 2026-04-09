from curl_cffi import requests
from datetime import datetime, date
from typing import List
from models import Activity
import base64

class IntervalsClient:
    def __init__(self, athlete_id: str, api_key: str):
        self.athlete_id = athlete_id
        self.api_key = api_key
        self.base_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
        auth_str = f"API_KEY:{api_key}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {encoded_auth}"
        }

    def get_activities(self, oldest: date, newest: date) -> List[Activity]:
        url = f"{self.base_url}/activities"
        params = {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat()
        }
        response = requests.get(url, headers=self.headers, params=params, impersonate="chrome")
        response.raise_for_status()
        
        activities = []
        for item in response.json():
            # start_date_local is ISO format like "2026-04-08T10:30:00"
            start_date_local = item["start_date_local"]
            start_time = datetime.fromisoformat(start_date_local.replace("Z", "+00:00"))
            
            # Gear info in Intervals might be in 'gear' object or field
            gear_item = item.get("gear", {})
            gear_id = None
            gear_name = None
            if isinstance(gear_item, dict):
                gear_id = str(gear_item.get("id")) if gear_item.get("id") else None
                gear_name = gear_item.get("name")
            else:
                # Fallback if it's just a string ID
                gear_id = str(gear_item) if gear_item else None
            
            activities.append(Activity(
                platform_id=str(item["id"]),
                name=item.get("name", "Unknown Activity"),
                start_time=start_time,
                duration_sec=item.get("elapsed_time", 0),
                type=item.get("type", "Unknown"),
                external_id=str(item.get("external_id")) if item.get("external_id") else None,
                source=item.get("source"),
                strava_id=str(item.get("strava_id")) if item.get("strava_id") else None,
                local_start_date_str=start_date_local,
                gear_id=gear_id,
                gear_name=gear_name
            ))
        return activities
