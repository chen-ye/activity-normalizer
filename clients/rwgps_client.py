from curl_cffi import requests
from datetime import date, datetime
from typing import List
from models import Activity

class RWGPSClient:
    def __init__(self, api_key: str, auth_token: str):
        self.api_key = api_key
        self.auth_token = auth_token
        self.base_url = "https://ridewithgps.com"

    def get_activities(self, oldest: date, newest: date) -> List[Activity]:
        url = f"{self.base_url}/trips.json"
        params = {
            "apikey": self.api_key,
            "version": 2,
            "auth_token": self.auth_token
        }
        response = requests.get(url, params=params, impersonate="chrome")
        response.raise_for_status()
        
        activities = []
        data = response.json()
        trips = data if isinstance(data, list) else data.get("results", [])
        
        for item in trips:
            # departed_at is something like "2026-04-08T10:30:00Z"
            departed_at = item["departed_at"]
            start_time = datetime.fromisoformat(departed_at.replace("Z", "+00:00"))
            if oldest <= start_time.date() <= newest:
                activities.append(Activity(
                    platform_id=str(item.get("id")),
                    name=item.get("name", "Unknown Trip"),
                    start_time=start_time,
                    duration_sec=item.get("duration", 0),
                    type="Ride",
                    local_start_date_str=departed_at # Store for exact matching
                ))
        return activities

    def update_activity_name(self, activity_id: str, new_name: str):
        url = f"{self.base_url}/trips/{activity_id}.json"
        params = {
            "apikey": self.api_key,
            "version": 2,
            "auth_token": self.auth_token
        }
        payload = {
            "trip": {
                "name": new_name
            }
        }
        response = requests.put(url, params=params, json=payload, impersonate="chrome")
        response.raise_for_status()
