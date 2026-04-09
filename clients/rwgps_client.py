import json
import os
from curl_cffi import requests
from datetime import date, datetime
from typing import List, Optional
from models import Activity

class RWGPSClient:
    def __init__(self, api_key: str, email: str = None, password: str = None, token_path: str = "rwgps_tokens.json"):
        self.api_key = api_key
        self.email = email
        self.password = password
        self.token_path = token_path
        self.auth_token = None
        self.base_url = "https://ridewithgps.com"
        
        self.authenticate()

    def authenticate(self):
        # 1. Try to load existing token
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r") as f:
                    data = json.load(f)
                    self.auth_token = data.get("auth_token", {}).get("auth_token") or data.get("auth_token")
                    if self.auth_token:
                        print(f"Restored Ride with GPS session from {self.token_path}")
                        return
            except Exception as e:
                print(f"Failed to load RWGPS token: {e}")

        # 2. Fetch new token if credentials provided
        if self.email and self.password:
            print("Fetching new Ride with GPS auth token...")
            url = f"{self.base_url}/api/v1/auth_tokens.json"
            headers = {
                "x-rwgps-api-key": self.api_key,
                "Accept": "application/json"
            }
            payload = {
                "user": {
                    "email": self.email,
                    "password": self.password
                }
            }
            response = requests.post(url, headers=headers, json=payload, impersonate="chrome")
            if response.status_code == 201:
                data = response.json()
                self.auth_token = data.get("auth_token", {}).get("auth_token")
                with open(self.token_path, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"Saved new Ride with GPS auth token to {self.token_path}")
            else:
                print(f"Failed to authenticate with Ride with GPS: {response.status_code} {response.text}")
                response.raise_for_status()
        else:
            raise ValueError("No valid Ride with GPS auth token found and no credentials provided.")

    @property
    def auth_headers(self):
        return {
            "x-rwgps-api-key": self.api_key,
            "x-rwgps-auth-token": self.auth_token,
            "Accept": "application/json",
            "x-rwgps-api-version": "3"
        }

    def get_activities(self, oldest: date, newest: date) -> List[Activity]:
        # Using the sync endpoint to fetch created/updated items since a specific date
        url = f"{self.base_url}/api/v1/sync.json"
        params = {
            "since": oldest.isoformat(),
            "assets": "trips"
        }
        response = requests.get(url, headers=self.auth_headers, params=params, impersonate="chrome")
        response.raise_for_status()

        activities = []
        data = response.json()

        items = data.get("items", [])

        for item in items:
            if item.get("item_type") != "trip" or item.get("action") == "deleted":
                continue

            item_url = item.get("item_url")
            if not item_url:
                continue

            # Fetch the actual trip details
            trip_response = requests.get(item_url, headers=self.auth_headers, impersonate="chrome")
            if trip_response.status_code != 200:
                print(f"Failed to fetch trip details from {item_url}: {trip_response.status_code}")
                continue

            trip_data = trip_response.json().get("trip")
            if not trip_data:
                continue

            departed_at = trip_data.get("departed_at")
            if not departed_at:
                continue

            # Parse as UTC datetime
            start_time = datetime.fromisoformat(departed_at.replace("Z", "+00:00"))

            # Filter by date range (using UTC date)
            if oldest <= start_time.date() <= newest:
                activities.append(Activity(
                    platform_id=str(trip_data.get("id")),
                    name=trip_data.get("name", "Unknown Trip"),
                    start_time=start_time,
                    duration_sec=trip_data.get("duration", 0),
                    type=trip_data.get("activity_type", "Ride"),
                    local_start_date_str=departed_at,
                    gear_id=str(trip_data.get("gear_id")) if trip_data.get("gear_id") else None
                ))
        return activities

    def update_activity(self, activity_id: str, name: str, gear_id: Optional[str] = None, activity_type: Optional[str] = None):
        # Using the direct trips endpoint with PATCH as suggested by user feedback
        url = f"{self.base_url}/trips/{activity_id}"
        trip_payload = {"name": name}
        if gear_id:
            trip_payload["gear_id"] = gear_id
        if activity_type:
            trip_payload["activity_type"] = activity_type
            
        payload = {"trip": trip_payload}
        response = requests.patch(url, headers=self.auth_headers, json=payload, impersonate="chrome")
        response.raise_for_status()
