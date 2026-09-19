from dataclasses import dataclass, field


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    title: str
    price: float | None
    neighborhood: str | None
    raw_address_text: str | None
    posted_at: str | None

    latitude: float | None = None
    longitude: float | None = None
    location_precision: str = "unknown"  # "exact" (from source geotag), "geocoded", "none"

    spam_flags: list[str] = field(default_factory=list)
    spam_score: int = 0

    # filled in by compliance.py, best-effort display value only:
    # {facility_type: distance_ft_to_nearest, or None if none found within
    # the largest configured buffer, or the query itself failed/was skipped}
    nearest_facility_ft: dict[str, float | None] = field(default_factory=dict)

    # filled in by compliance.py, the actual source of truth for clears_buffer:
    # {facility_type: {buffer_ft: True/False/None}}. None means "couldn't be
    # verified" (failed query, or no location data) -- never treated as a pass.
    facility_clearance: dict[str, dict[int, bool | None]] = field(default_factory=dict)

    def is_affordable(self, max_rent: float) -> bool:
        return self.price is not None and self.price <= max_rent

    def clears_buffer(self, buffer_ft: int, facility_types: tuple[str, ...]) -> bool | None:
        """False if any facility type is confirmed too close, None if any
        facility type couldn't be verified at this tier, True only if every
        facility type was checked and came back clear."""
        results = [self.facility_clearance.get(ftype, {}).get(buffer_ft) for ftype in facility_types]
        if any(result is False for result in results):
            return False
        if any(result is None for result in results):
            return None
        return True
