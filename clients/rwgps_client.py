import json
import os
from curl_cffi import requests
from datetime import date, datetime
from typing import List
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
                    # Support both nested and flat token storage
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
        # Using the base trips.json endpoint which returns the 100 most recent trips
        url = f"{self.base_url}/api/v1/trips.json"
        params = {
            "page": 1,
            "page_size": 20
        }
        response = requests.get(url, headers=self.auth_headers, params=params, impersonate="chrome")
        response.raise_for_status()
        
        activities = []
        data = response.json()
        
        # API v1 uses 'trips' key, some endpoints use 'results'
        trips = data.get("trips") or data.get("results")
        if trips is None and isinstance(data, list):
            trips = data
        
        if not trips:
            return []
        
        for item in trips:
            departed_at = item.get("departed_at")
            if not departed_at:
                continue
            
            # Parse as UTC datetime
            start_time = datetime.fromisoformat(departed_at.replace("Z", "+00:00"))
            
            # Filter by date range (using UTC date)
            if oldest <= start_time.date() <= newest:
                activities.append(Activity(
                    platform_id=str(item.get("id")),
                    name=item.get("name", "Unknown Trip"),
                    start_time=start_time,
                    duration_sec=item.get("duration", 0),
                    type="Ride",
                    local_start_date_str=departed_at
                ))
        return activities

    def update_activity_name(self, activity_id: str, new_name: str):
        # Using the direct trips endpoint with PATCH as suggested by user feedback
        url = f"{self.base_url}/trips/{activity_id}"
        payload = {
            "trip": {
                "name": new_name
            }
        }
        response = requests.patch(url, headers=self.auth_headers, json=payload, impersonate="chrome")
        response.raise_for_status()
