import os
import argparse
import json
import zipfile
import requests
from datetime import date, timedelta
from dotenv import load_dotenv

from clients.intervals_client import IntervalsClient
from clients.garmin_client import GarminClient
from clients.rwgps_client import RWGPSClient
from synchronizer import ActivitySynchronizer

def download_and_extract_gc_export(url: str):
    cache_dir = "download_cache"
    os.makedirs(cache_dir, exist_ok=True)
    zip_path = os.path.join(cache_dir, "gc_export_cached.zip")
    
    if not os.path.exists(zip_path):
        print(f"Downloading Garmin Connect export from {url}...")
        try:
            # Using standard requests here for the large download
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                total_length = int(r.headers.get("content-length", 0))
                with open(zip_path, 'wb') as f:
                    from rich.progress import Progress, DownloadColumn, TransferSpeedColumn, TextColumn, BarColumn, TimeRemainingColumn
                    with Progress(
                        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
                        BarColumn(bar_width=None),
                        "[progress.percentage]{task.percentage:>3.1f}%",
                        "•",
                        DownloadColumn(),
                        "•",
                        TransferSpeedColumn(),
                        "•",
                        TimeRemainingColumn(),
                    ) as progress:
                        task = progress.add_task("Downloading...", filename="gc_export_cached.zip", total=total_length or None)
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
            print(f"Downloaded Garmin export to {zip_path}")
        except Exception as e:
            print(f"Error downloading Garmin export: {e}")
            return
    else:
        print(f"Using cached Garmin export: {zip_path}")

    print("Extracting summarized activities from zip...")
    export_dir = "gc-export"
    os.makedirs(export_dir, exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            count = 0
            for file_info in zip_ref.infolist():
                if file_info.filename.endswith("_summarizedActivities.json"):
                    # Extract to the gc-export folder, flattening the directory structure
                    # Get just the filename
                    filename = os.path.basename(file_info.filename)
                    if not filename:
                        continue
                    
                    target_path = os.path.join(export_dir, filename)
                    with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                        target.write(source.read())
                    count += 1
            print(f"Extracted {count} activity summary files to {export_dir}/")
    except Exception as e:
        print(f"Error extracting Garmin export: {e}")

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Normalize activity names across platforms.")
    parser.add_argument("--days", type=int, default=7, help="Number of days to sync back (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Do not actually update activities")
    parser.add_argument("--offline-garmin", action="store_true", help="Disable direct Garmin API usage and output gc-changes.json")
    parser.add_argument("--offline-rwgps", action="store_true", help="Disable direct RWGPS API usage and output rwgps-changes.json")
    parser.add_argument("--gc-export-url", type=str, help="URL to download and extract Garmin Connect GDPR export zip")
    args = parser.parse_args()

    # Handle GC Export Download/Extraction first
    if args.gc_export_url:
        download_and_extract_gc_export(args.gc_export_url)

    # Load credentials from environment
    intervals_athlete_id = os.getenv("INTERVALS_ATHLETE_ID")
    intervals_api_key = os.getenv("INTERVALS_API_KEY")
    
    # Common check
    if not all([intervals_athlete_id, intervals_api_key]):
        print("Error: Missing core Intervals.icu credentials in .env file.")
        return

    garmin_client = None
    if not args.offline_garmin:
        garmin_email = os.getenv("GARMIN_EMAIL")
        garmin_password = os.getenv("GARMIN_PASSWORD")
        if not all([garmin_email, garmin_password]):
            print("Error: Missing Garmin credentials for online mode. Please check your .env file.")
            return
        garmin_client = GarminClient(garmin_email, garmin_password)

    rwgps_client = None
    if not args.offline_rwgps:
        rwgps_api_key = os.getenv("RWGPS_API_KEY")
        rwgps_email = os.getenv("RWGPS_EMAIL")
        rwgps_password = os.getenv("RWGPS_PASSWORD")
        if not all([rwgps_api_key, rwgps_email, rwgps_password]):
            print("Error: Missing RWGPS credentials for online mode. Please check your .env file.")
            return
        rwgps_client = RWGPSClient(rwgps_api_key, rwgps_email, rwgps_password)

    # Initialize truth client
    intervals_client = IntervalsClient(intervals_athlete_id, intervals_api_key)

    # Initialize and run synchronizer
    sync = ActivitySynchronizer(intervals_client, garmin_client, rwgps_client)
    
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    
    sync.sync_names(
        start_date, 
        end_date, 
        dry_run=args.dry_run, 
        offline_garmin=args.offline_garmin,
        offline_rwgps=args.offline_rwgps
    )

if __name__ == "__main__":
    main()
