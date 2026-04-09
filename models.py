from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

@dataclass
class Activity:
    platform_id: str
    name: str
    start_time: datetime
    duration_sec: int
    type: str
    # New fields for deterministic matching and gear
    external_id: Optional[str] = None
    source: Optional[str] = None
    strava_id: Optional[str] = None
    local_start_date_str: Optional[str] = None # Exact ISO string from API
    gear_id: Optional[str] = None
    gear_name: Optional[str] = None
    description: Optional[str] = None

    def matches(self, other: 'Activity') -> bool:
        """
        Fuzzy match fallback. Handles naive vs aware datetimes by converting both to UTC.
        """
        # Ensure self.start_time is aware (assume UTC if naive)
        s_time = self.start_time
        if s_time.tzinfo is None:
            s_time = s_time.replace(tzinfo=timezone.utc)
            
        # Ensure other.start_time is aware (assume UTC if naive)
        o_time = other.start_time
        if o_time.tzinfo is None:
            o_time = o_time.replace(tzinfo=timezone.utc)

        time_diff = abs((s_time - o_time).total_seconds())
        return time_diff <= 120
