import os
import argparse
from datetime import date, timedelta
from dotenv import load_dotenv

from clients.intervals_client import IntervalsClient
from clients.garmin_client import GarminClient
from clients.rwgps_client import RWGPSClient
from synchronizer import ActivitySynchronizer

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Normalize activity names across platforms.")
    parser.add_argument("--days", type=int, default=7, help="Number of days to sync back (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Do not actually update activities")
    parser.add_argument("--offline-garmin", action="store_true", help="Disable direct Garmin API usage and output gc-changes.json")
    args = parser.parse_args()

    # Load credentials from environment
    intervals_athlete_id = os.getenv("INTERVALS_ATHLETE_ID")
    intervals_api_key = os.getenv("INTERVALS_API_KEY")
    
    rwgps_api_key = os.getenv("RWGPS_API_KEY")
    rwgps_email = os.getenv("RWGPS_EMAIL")
    rwgps_password = os.getenv("RWGPS_PASSWORD")

    garmin_client = None
    if not args.offline_garmin:
        garmin_email = os.getenv("GARMIN_EMAIL")
        garmin_password = os.getenv("GARMIN_PASSWORD")
        if not all([intervals_athlete_id, intervals_api_key, garmin_email, garmin_password, rwgps_api_key, rwgps_email, rwgps_password]):
            print("Error: Missing environment variables for online mode. Please check your .env file.")
            return
        garmin_client = GarminClient(garmin_email, garmin_password)
    else:
        if not all([intervals_athlete_id, intervals_api_key, rwgps_api_key, rwgps_email, rwgps_password]):
            print("Error: Missing environment variables for offline mode. Please check your .env file.")
            return

    # Initialize clients
    intervals_client = IntervalsClient(intervals_athlete_id, intervals_api_key)
    rwgps_client = RWGPSClient(rwgps_api_key, rwgps_email, rwgps_password)

    # Initialize and run synchronizer
    sync = ActivitySynchronizer(intervals_client, garmin_client, rwgps_client)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    
    sync.sync_names(start_date, end_date, dry_run=args.dry_run, offline_garmin=args.offline_garmin)

if __name__ == "__main__":
    main()
