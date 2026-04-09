from datetime import datetime, timedelta
from models import Activity

def test_activity_matches():
    a1 = Activity(
        platform_id="1",
        name="Morning Ride",
        start_time=datetime(2026, 4, 8, 10, 0, 0),
        duration_sec=3600,
        type="Ride",
        local_start_date_str="2026-04-08T10:00:00"
    )
    
    # Same start time
    a2 = Activity(
        platform_id="2",
        name="10:00 Ride",
        start_time=datetime(2026, 4, 8, 10, 0, 0),
        duration_sec=3605,
        type="Ride",
        local_start_date_str="2026-04-08T10:00:00Z"
    )

    # Test the fuzzy match (used as fallback)
    assert a1.matches(a2)
    
    # Test deterministic string match logic (as implemented in synchronizer)
    truth_iso = a1.local_start_date_str.split('Z')[0]
    target_iso = a2.local_start_date_str.split('Z')[0]
    assert truth_iso == target_iso
