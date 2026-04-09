import json
import os
import re
try:
    import readline
except ImportError:
    pass
from datetime import date
from typing import List, Optional, Dict
from clients.intervals_client import IntervalsClient
from clients.garmin_client import GarminClient
from clients.rwgps_client import RWGPSClient
from models import Activity

# Mapping Intervals.icu/Strava types to Garmin Connect activity types
ICU_TO_GC_TYPES = {
    "Ride": "cycling",
    "Run": "running",
    "Walk": "walking",
    "Hike": "hiking",
    "VirtualRide": "virtual_ride",
    "EBikeRide": "e_bike_fitness",
    "MountainBikeRide": "mountain_biking",
    "GravelRide": "gravel_cycling",
    "Swim": "swimming",
    "WeightTraining": "strength_training",
    "Yoga": "yoga",
    "Workout": "indoor_cardio",
    "NordicSki": "cross_country_skiing_ws",
    "AlpineSki": "resort_skiing",
    "IceSkate": "skating_ws",
    "InlineSkate": "inline_skating",
    "RockClimbing": "rock_climbing",
    "StairStepper": "stair_climbing",
    "Rowing": "indoor_rowing",
    "Kayaking": "kayaking_v2",
    "Canoeing": "paddling_v2",
    "Sailing": "sailing_v2",
    "Surfing": "surfing",
    "StandUpPaddling": "stand_up_paddleboarding_v2",
    "Windsurf": "windsurfing",
    "Elliptical": "elliptical",
    "Pilates": "pilates",
    "Snowshoe": "snow_shoe_ws",
    "Handcycle": "hand_cycling"
}

# Mapping Intervals.icu/Strava types to Ride with GPS activity types
ICU_TO_RWGPS_TYPES = {
    "Ride": "cycling:road",
    "GravelRide": "cycling:gravel",
    "MountainBikeRide": "cycling:mountain",
    "VirtualRide": "cycling:generic",
    "EBikeRide": "cycling:generic",
    "Run": "running:generic",
    "Walk": "walking:generic",
    "Hike": "walking:hiking",
    "Swim": "swimming:generic"
}

class ActivitySynchronizer:
    def __init__(self, intervals: IntervalsClient, garmin: Optional[GarminClient], rwgps: Optional[RWGPSClient]):
        self.intervals = intervals
        self.garmin = garmin
        self.rwgps = rwgps
        self.gear_mapping_file = "gear-mappings.json"
        self.gear_mappings = self._load_gear_mappings()
        # Pattern to ignore default Strava activity names (Morning Ride, Afternoon Run, etc.)
        self.default_name_pattern = re.compile(
            r"^(Morning|Lunch|Afternoon|Evening|Night) (Ride|Run|Walk|Hike|Swim|Workout|Weight Training|Yoga|Activity|Cycle|Gravel Ride|E-Bike Ride|Mountain Bike Ride|Virtual Ride|Trip|Session).*",
            re.IGNORECASE
        )

    def _load_gear_mappings(self) -> Dict[str, Dict[str, str]]:
        if os.path.exists(self.gear_mapping_file):
            with open(self.gear_mapping_file, "r") as f:
                return json.load(f)
        return {}

    def _save_gear_mappings(self):
        with open(self.gear_mapping_file, "w") as f:
            json.dump(self.gear_mappings, f, indent=2)

    def _get_garmin_gear_id(self, truth: Activity) -> str:
        if not truth.gear_id:
            return ""
        
        if truth.gear_id in self.gear_mappings and "garmin_connect_id" in self.gear_mappings[truth.gear_id]:
            return self.gear_mappings[truth.gear_id].get("garmin_connect_id", "")
        
        # Mapping missing, prompt user
        gear_name = truth.gear_name or f"ID {truth.gear_id}"
        print(f"\nGarmin mapping missing for Intervals.icu gear: {gear_name} ({truth.gear_id})")
        gc_id = input(f"Enter Garmin Connect gear ID for {gear_name}: ").strip()
        
        if truth.gear_id not in self.gear_mappings:
            self.gear_mappings[truth.gear_id] = {}
        self.gear_mappings[truth.gear_id]["garmin_connect_id"] = gc_id
        self._save_gear_mappings()
        return gc_id

    def _get_rwgps_gear_id(self, truth: Activity) -> str:
        if not truth.gear_id:
            return ""
        
        if truth.gear_id in self.gear_mappings and "rwgps_id" in self.gear_mappings[truth.gear_id]:
            return self.gear_mappings[truth.gear_id].get("rwgps_id", "")
        
        # Mapping missing, prompt user
        gear_name = truth.gear_name or f"ID {truth.gear_id}"
        print(f"\nRWGPS mapping missing for Intervals.icu gear: {gear_name} ({truth.gear_id})")
        rwgps_id = input(f"Enter Ride with GPS gear ID for {gear_name}: ").strip()
        
        if truth.gear_id not in self.gear_mappings:
            self.gear_mappings[truth.gear_id] = {}
        self.gear_mappings[truth.gear_id]["rwgps_id"] = rwgps_id
        self._save_gear_mappings()
        return rwgps_id

    def _is_invalid_name(self, name: Optional[str]) -> bool:
        if not name or not name.strip():
            return True
        if name.lower() == "unknown activity":
            return True
        return bool(self.default_name_pattern.match(name))

    def _map_to_gc_type(self, icu_type: str) -> str:
        return ICU_TO_GC_TYPES.get(icu_type, "uncategorized")

    def _map_to_rwgps_type(self, icu_type: str) -> str:
        return ICU_TO_RWGPS_TYPES.get(icu_type, "cycling:generic")

    def sync_names(self, start_date: date, end_date: date, dry_run: bool = True, offline_garmin: bool = False, offline_rwgps: bool = False):
        print(f"Syncing from {start_date} to {end_date} (Dry run: {dry_run}, Offline Garmin: {offline_garmin}, Offline RWGPS: {offline_rwgps})")
        
        # 1. Get truth from Intervals.icu
        raw_truth_activities = self.intervals.get_activities(start_date, end_date)
        
        # Filter out default Strava names and invalid records
        truth_activities = [a for a in raw_truth_activities if not self._is_invalid_name(a.name)]
        ignored_count = len(raw_truth_activities) - len(truth_activities)
        
        print(f"Found {len(raw_truth_activities)} high-quality activities in Intervals.icu ({ignored_count} ignored as default/invalid names)")
        
        if not truth_activities:
            print("No valid activities to sync.")
            return

        # 2. Fetch targets
        rwgps_activities = []
        if offline_rwgps:
            print("Skipping Ride with GPS fetch (Offline Mode)")
        else:
            rwgps_activities = self.rwgps.get_activities(start_date, end_date)
            print(f"Found {len(rwgps_activities)} activities in Ride with GPS")

        garmin_activities = []
        if offline_garmin:
            print("Skipping Garmin Connect fetch (Offline Mode)")
        else:
            garmin_activities = self.garmin.get_activities(start_date, end_date)
            print(f"Found {len(garmin_activities)} activities in Garmin Connect")

        gc_changes = []
        rwgps_changes = []

        for truth in truth_activities:
            # Handle Garmin Sync
            if offline_garmin:
                if truth.source in ["GARMIN", "GARMIN_CONNECT"] and truth.external_id:
                    gc_gear_id = self._get_garmin_gear_id(truth)
                    gc_changes.append({
                        "garmin_activity_id": truth.external_id,
                        "name": truth.name,
                        "gear_id": gc_gear_id,
                        "activity_type": self._map_to_gc_type(truth.type)
                    })
            else:
                self._sync_garmin(truth, garmin_activities, dry_run)
            
            # Handle RWGPS Sync
            if offline_rwgps:
                rwgps_gear_id = self._get_rwgps_gear_id(truth)
                rwgps_changes.append({
                    "name": truth.name,
                    "local_start_date_str": truth.local_start_date_str,
                    "start_time": truth.start_time.isoformat() if truth.start_time else None,
                    "duration_sec": truth.duration_sec,
                    "activity_type": self._map_to_rwgps_type(truth.type),
                    "gear_id": rwgps_gear_id
                })
            else:
                self._sync_rwgps(truth, rwgps_activities, dry_run)
        
        if offline_garmin:
            with open("gc-changes.json", "w") as f:
                json.dump(gc_changes, f, indent=2)
            print(f"Wrote {len(gc_changes)} activities to gc-changes.json for asynchronous processing")

        if offline_rwgps:
            with open("rwgps-changes.json", "w") as f:
                json.dump(rwgps_changes, f, indent=2)
            print(f"Wrote {len(rwgps_changes)} activities to rwgps-changes.json for asynchronous processing")

    def _sync_garmin(self, truth: Activity, garmin_list: List[Activity], dry_run: bool):
        target_match = None
        if truth.source in ["GARMIN", "GARMIN_CONNECT"] and truth.external_id:
            for g in garmin_list:
                if g.platform_id == truth.external_id:
                    target_match = g
                    break
        
        if not target_match:
            for g in garmin_list:
                if truth.matches(g):
                    target_match = g
                    break
        
        if target_match:
            self._apply_update_garmin(truth, target_match, self.garmin, dry_run)
        else:
            print(f"[Garmin] No match found for '{truth.name}' ({truth.start_time} UTC)")

    def _sync_rwgps(self, truth: Activity, rwgps_list: List[Activity], dry_run: bool):
        target_match = None
        truth_iso = truth.local_start_date_str.replace('Z', '').split('+')[0] if truth.local_start_date_str else ""
        
        for r in rwgps_list:
            rwgps_iso = r.local_start_date_str.replace('Z', '').split('+')[0] if r.local_start_date_str else ""
            if truth_iso == rwgps_iso:
                target_match = r
                break
        
        if not target_match:
            for r in rwgps_list:
                if truth.matches(r):
                    target_match = r
                    break
        
        if target_match:
            self._apply_update_rwgps(truth, target_match, self.rwgps, dry_run)
        else:
            print(f"[Ride with GPS] No match found for '{truth.name}' ({truth.start_time} UTC)")

    def _apply_update_garmin(self, truth: Activity, target: Activity, client, dry_run: bool):
        if truth.name != target.name:
            print(f"[Garmin] Updating name: '{target.name}' -> '{truth.name}'")
            if not dry_run:
                try:
                    client.update_activity_name(target.platform_id, truth.name)
                except Exception as e:
                    print(f"[Garmin] Error updating {target.platform_id}: {e}")
        else:
            print(f"[Garmin] Name already matches: '{truth.name}'")

    def _apply_update_rwgps(self, truth: Activity, target: Activity, client, dry_run: bool):
        rwgps_type = self._map_to_rwgps_type(truth.type)
        rwgps_gear_id = self._get_rwgps_gear_id(truth)
        
        # We check for differences in name, type, and gear
        needs_update = (
            truth.name != target.name or
            rwgps_type != target.type or
            (rwgps_gear_id and rwgps_gear_id != target.gear_id)
        )
        
        if needs_update:
            print(f"[Ride with GPS] Updating: name='{truth.name}', type='{rwgps_type}', gear='{rwgps_gear_id}'")
            if not dry_run:
                try:
                    client.update_activity(target.platform_id, name=truth.name, gear_id=rwgps_gear_id, activity_type=rwgps_type)
                except Exception as e:
                    print(f"[Ride with GPS] Error updating {target.platform_id}: {e}")
        else:
            print(f"[Ride with GPS] Already matches: '{truth.name}'")
