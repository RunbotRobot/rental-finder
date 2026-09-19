from rental_finder.config import Settings
from rental_finder.geocode import GeocodeResult, county_for_point, geocode_address, is_plausible
from rental_finder.models import has_street_number


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params))
        return _FakeResponse(self.payload)


def test_county_for_point_reads_census_geographies():
    session = _FakeSession({"result": {"geographies": {"Counties": [{"NAME": "King County"}]}}})
    assert county_for_point(47.44, -122.30, Settings(), session) == "King County"


def test_geocode_address_reads_county_and_state():
    session = _FakeSession({"result": {"addressMatches": [{
        "coordinates": {"x": -122.31, "y": 47.35},
        "geographies": {"Counties": [{"NAME": "King County"}], "States": [{"NAME": "Washington"}]},
    }]}})
    result = geocode_address("28620 Pacific Hwy S, Federal Way, WA", Settings(), session)
    assert (result.latitude, result.longitude, result.county, result.state) == (47.35, -122.31, "King County", "Washington")


def test_out_of_state_geocode_is_rejected():
    weld_county_co = GeocodeResult(latitude=40.4, longitude=-104.7, county="Weld County", state="Colorado")
    assert not is_plausible(weld_county_co, pin_lat=47.61, pin_lon=-122.31)
    assert not is_plausible(weld_county_co, pin_lat=None, pin_lon=None)


def test_geocode_far_from_craigslist_pin_is_rejected():
    spokane = GeocodeResult(latitude=47.66, longitude=-117.43, county="Spokane County", state="Washington")
    assert not is_plausible(spokane, pin_lat=47.61, pin_lon=-122.31)


def test_nearby_washington_geocode_is_accepted():
    seattle = GeocodeResult(latitude=47.618, longitude=-122.347, county="King County", state="Washington")
    assert is_plausible(seattle, pin_lat=47.6151, pin_lon=-122.3447)
    assert is_plausible(seattle, pin_lat=None, pin_lon=None)
    assert is_plausible(GeocodeResult(47.6, -122.3, None, None), None, None)


def test_street_addresses_qualify():
    assert has_street_number("2619 5th Avenue, Seattle, WA")
    assert has_street_number("28620 Pacific Hwy S, Federal Way, WA")
    assert has_street_number("717 N 178th St, Shoreline, WA")
    assert has_street_number("123B Main St")


def test_area_names_do_not():
    assert not has_street_number("Seattle, WA")
    assert not has_street_number("Belltown / Downtown Seattle")
    assert not has_street_number("shoreline")
    assert not has_street_number("")
    assert not has_street_number(None)


def test_bare_number_is_not_an_address():
    assert not has_street_number("98188")
