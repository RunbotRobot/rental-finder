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

    # filled in by compliance.py: {facility_type: distance_ft_to_nearest or None}
    nearest_facility_ft: dict[str, float | None] = field(default_factory=dict)

    def is_affordable(self, max_rent: float) -> bool:
        return self.price is not None and self.price <= max_rent

    def clears_buffer(self, buffer_ft: int, facility_types: tuple[str, ...]) -> bool | None:
        """True/False if we have distance data for all required facility types,
        None if we couldn't determine location well enough to say."""
        if self.location_precision == "none":
            return None
        for ftype in facility_types:
            dist = self.nearest_facility_ft.get(ftype)
            if dist is not None and dist < buffer_ft:
                return False
        return True
