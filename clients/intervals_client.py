from curl_cffi import requests
from datetime import datetime, date
from typing import List, Dict
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
        self._gear_map = None

    def _get_gear_map(self) -> Dict[str, str]:
        if self._gear_map is not None:
            return self._gear_map
        
        print("Fetching Intervals.icu gear list for name resolution...")
        url = f"{self.base_url}/gear"
        response = requests.get(url, headers=self.headers, impersonate="chrome")
        response.raise_for_status()
        
        self._gear_map = {str(item["id"]): item["name"] for item in response.json()}
        return self._gear_map

    def get_activities(self, oldest: date, newest: date) -> List[Activity]:
        url = f"{self.base_url}/activities"
        params = {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat()
        }
        response = requests.get(url, headers=self.headers, params=params, impersonate="chrome")
        response.raise_for_status()
        
        gear_map = self._get_gear_map()
        activities = []
        for item in response.json():
            # Skip records from STRAVA as they lack metadata in the API
            if item.get("source") == "STRAVA":
                continue

            # Skip records that don't have a linked Strava ID (since strava is manually curated + source of truth)
            if item.get("strava_id") is None:
                continue
                
            # Skip malformed records without names or dates
            name = item.get("name")
            start_date_utc = item.get("start_date")
            start_date_local = item.get("start_date_local")
            
            if not name or not (start_date_utc or start_date_local):
                continue
            
            # Use UTC if available, otherwise local
            date_to_use = start_date_utc or start_date_local
            start_time = datetime.fromisoformat(date_to_use.replace("Z", "+00:00"))
            
            gear_item = item.get("gear", {})
            gear_id = None
            if isinstance(gear_item, dict):
                gear_id = str(gear_item.get("id")) if gear_item.get("id") else None
            else:
                gear_id = str(gear_item) if gear_item else None
            
            # Resolve gear name from our map
            gear_name = gear_map.get(gear_id) if gear_id else None
            
            activities.append(Activity(
                platform_id=str(item.get("id")),
                name=name,
                start_time=start_time,
                duration_sec=item.get("elapsed_time", 0),
                type=item.get("type", "Unknown"),
                external_id=str(item.get("external_id")) if item.get("external_id") else None,
                source=item.get("source"),
                strava_id=str(item.get("strava_id")) if item.get("strava_id") else None,
                local_start_date_str=date_to_use, 
                gear_id=gear_id,
                gear_name=gear_name
            ))
        return activities
