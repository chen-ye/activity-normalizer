from dataclasses import dataclass
from datetime import datetime
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

    def matches(self, other: 'Activity') -> bool:
        """
        Fuzzy match fallback.
        """
        time_diff = abs((self.start_time - other.start_time).total_seconds())
        return time_diff <= 120
