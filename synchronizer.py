import json
import os
from datetime import date
from typing import List, Optional, Dict
from clients.intervals_client import IntervalsClient
from clients.garmin_client import GarminClient
from clients.rwgps_client import RWGPSClient
from models import Activity

class ActivitySynchronizer:
    def __init__(self, intervals: IntervalsClient, garmin: Optional[GarminClient], rwgps: RWGPSClient):
        self.intervals = intervals
        self.garmin = garmin
        self.rwgps = rwgps
        self.gear_mapping_file = "gear-mappings.json"
        self.gear_mappings = self._load_gear_mappings()

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
        
        if truth.gear_id in self.gear_mappings:
            return self.gear_mappings[truth.gear_id].get("garmin_connect_id", "")
        
        # Mapping missing, prompt user
        gear_name = truth.gear_name or f"ID {truth.gear_id}"
        print(f"\nGear mapping missing for Intervals.icu gear: {gear_name} ({truth.gear_id})")
        gc_id = input(f"Enter Garmin Connect gear ID for {gear_name}: ").strip()
        
        self.gear_mappings[truth.gear_id] = {"garmin_connect_id": gc_id}
        self._save_gear_mappings()
        return gc_id

    def sync_names(self, start_date: date, end_date: date, dry_run: bool = True, offline_garmin: bool = False):
        print(f"Syncing from {start_date} to {end_date} (Dry run: {dry_run}, Offline Garmin: {offline_garmin})")
        
        # 1. Get truth from Intervals.icu
        truth_activities = self.intervals.get_activities(start_date, end_date)
        print(f"Found {len(truth_activities)} activities in Intervals.icu")
        
        if not truth_activities:
            return

        # 2. Fetch targets
        rwgps_activities = self.rwgps.get_activities(start_date, end_date)
        print(f"Found {len(rwgps_activities)} activities in Ride with GPS")

        gc_changes = []
        
        garmin_activities = []
        if offline_garmin:
            print("Skipping Garmin Connect fetch (Offline Mode)")
        else:
            garmin_activities = self.garmin.get_activities(start_date, end_date)
            print(f"Found {len(garmin_activities)} activities in Garmin Connect")

        for truth in truth_activities:
            # Handle Garmin Sync
            if offline_garmin:
                if truth.source == "GARMIN" and truth.external_id:
                    gc_gear_id = self._get_garmin_gear_id(truth)
                    gc_changes.append({
                        "garmin_activity_id": truth.external_id,
                        "name": truth.name,
                        "gear_id": gc_gear_id,
                        "activity_type": truth.type
                    })
            else:
                self._sync_garmin(truth, garmin_activities, dry_run)
            
            # Sync RWGPS
            self._sync_rwgps(truth, rwgps_activities, dry_run)
        
        if offline_garmin:
            with open("gc-changes.json", "w") as f:
                json.dump(gc_changes, f, indent=2)
            print(f"Wrote {len(gc_changes)} activities to gc-changes.json for asynchronous processing")

    def _sync_garmin(self, truth: Activity, garmin_list: List[Activity], dry_run: bool):
        # GARMIN MATCHING: Use external_id if source is GARMIN
        target_match = None
        if truth.source == "GARMIN" and truth.external_id:
            for g in garmin_list:
                if g.platform_id == truth.external_id:
                    target_match = g
                    break
        
        # Fallback to fuzzy time match
        if not target_match:
            for g in garmin_list:
                if truth.matches(g):
                    target_match = g
                    break
        
        if target_match:
            self._apply_update(truth, target_match, self.garmin, "Garmin", dry_run)
        else:
            print(f"[Garmin] No match found for '{truth.name}' ({truth.start_time})")

    def _sync_rwgps(self, truth: Activity, rwgps_list: List[Activity], dry_run: bool):
        # RWGPS MATCHING: Compare ISO date strings directly
        target_match = None
        # Normalizing RWGPS '2026-04-08T10:30:00Z' and Intervals '2026-04-08T10:30:00'
        truth_iso = truth.local_start_date_str.split('Z')[0] if truth.local_start_date_str else ""
        
        for r in rwgps_list:
            rwgps_iso = r.local_start_date_str.split('Z')[0] if r.local_start_date_str else ""
            if truth_iso == rwgps_iso:
                target_match = r
                break
        
        # Fallback to fuzzy match
        if not target_match:
            for r in rwgps_list:
                if truth.matches(r):
                    target_match = r
                    break
        
        if target_match:
            self._apply_update(truth, target_match, self.rwgps, "Ride with GPS", dry_run)
        else:
            print(f"[Ride with GPS] No match found for '{truth.name}' ({truth.start_time})")

    def _apply_update(self, truth: Activity, target: Activity, client, platform_name: str, dry_run: bool):
        if truth.name != target.name:
            print(f"[{platform_name}] Updating name: '{target.name}' -> '{truth.name}'")
            if not dry_run:
                try:
                    client.update_activity_name(target.platform_id, truth.name)
                except Exception as e:
                    print(f"[{platform_name}] Error updating {target.platform_id}: {e}")
        else:
            print(f"[{platform_name}] Name already matches: '{truth.name}'")
