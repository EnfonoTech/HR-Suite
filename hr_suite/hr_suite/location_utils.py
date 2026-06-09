"""
location_utils.py
Geo-reference utilities for Attendance Location management.
Mobile-specific APIs have been removed. These functions support the
AttendanceLocation doctype validate/save hooks.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import frappe
from frappe import _

try:
	import openlocationcode as olc
except ImportError:
	olc = None


def build_geolocation(latitude, longitude, radius):
	"""
	Build a Frappe-compatible GeoJSON FeatureCollection string for a location point.

	Args:
		latitude (float): Latitude
		longitude (float): Longitude
		radius (int|None): Allowed radius in metres (defaults to 100)

	Returns:
		str: JSON-serialised GeoJSON FeatureCollection
	"""
	return frappe.as_json(
		{
			"type": "FeatureCollection",
			"features": [
				{
					"type": "Feature",
					"properties": {
						"point_type": "circle",
						"radius": int(radius or 100),
					},
					"geometry": {
						"type": "Point",
						"coordinates": [float(longitude), float(latitude)],
					},
				}
			],
		}
	)


def extract_coordinates_from_geolocation(geolocation):
	"""
	Extract (latitude, longitude) from a Frappe GeoJSON string or dict.

	Returns:
		tuple: (latitude, longitude) or (None, None) if not parseable
	"""
	if not geolocation:
		return (None, None)

	data = geolocation
	if isinstance(geolocation, str):
		try:
			data = json.loads(geolocation)
		except json.JSONDecodeError:
			return (None, None)

	features = data.get("features") or []
	for feature in features:
		geometry = feature.get("geometry") or {}
		coordinates = geometry.get("coordinates") or []
		if geometry.get("type") == "Point" and len(coordinates) >= 2:
			return (float(coordinates[1]), float(coordinates[0]))

	return (None, None)


def normalize_plus_code(value):
	"""Normalise a Plus Code string to uppercase with consistent spacing."""
	return " ".join((value or "").upper().split())


def encode_plus_code(latitude, longitude):
	"""Encode coordinates as a Plus Code. Returns None if library is unavailable."""
	if not olc:
		return None
	return olc.encode(float(latitude), float(longitude))


def _geocode_query(query):
	"""
	Geocode a free-text query via Nominatim.

	Returns:
		dict|None: {'latitude': float, 'longitude': float} or None on failure
	"""
	if not query:
		return None

	params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": 1})
	req = urllib.request.Request(
		"https://nominatim.openstreetmap.org/search?" + params,
		headers={"User-Agent": "hr_suite/1.0 attendance-location"},
	)
	try:
		with urllib.request.urlopen(req, timeout=8) as response:
			payload = json.loads(response.read().decode("utf-8"))
	except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
		return None

	if not payload:
		return None

	result = payload[0]
	return {"latitude": float(result["lat"]), "longitude": float(result["lon"])}


def _resolve_plus_code(plus_code, reference_latitude=None, reference_longitude=None, address_reference=None):
	"""
	Resolve a Plus Code (full or short) to coordinates.

	Returns:
		dict: {'latitude', 'longitude', 'plus_code', 'location_source'}
	"""
	if not olc:
		frappe.throw(
			_("Plus Code library not installed. Install openlocationcode and try again."),
			title=_("Plus Code Library Missing"),
		)

	normalized = normalize_plus_code(plus_code)

	if "+" not in normalized:
		frappe.throw(_("Invalid Plus Code format."), title=_("Invalid Plus Code"))

	if olc.isFull(normalized):
		decoded = olc.decode(normalized)
		return {
			"latitude": decoded.latitudeCenter,
			"longitude": decoded.longitudeCenter,
			"plus_code": normalized,
			"location_source": "Plus Code",
		}

	# Short Plus Code — try to recover using reference coordinates
	if reference_latitude is not None and reference_longitude is not None:
		full_code = olc.recoverNearest(normalized, float(reference_latitude), float(reference_longitude))
		decoded = olc.decode(full_code)
		return {
			"latitude": decoded.latitudeCenter,
			"longitude": decoded.longitudeCenter,
			"plus_code": full_code,
			"location_source": "Plus Code",
		}

	# Try geocoding the reference address combined with the short code
	query = " ".join(
		part for part in (normalized, (address_reference or "").strip()) if part
	).strip()
	geocoded = _geocode_query(query)
	if geocoded:
		resolved_plus_code = encode_plus_code(geocoded["latitude"], geocoded["longitude"])
		return {
			"latitude": geocoded["latitude"],
			"longitude": geocoded["longitude"],
			"plus_code": resolved_plus_code or normalized,
			"location_source": "Plus Code + Locality",
		}

	frappe.throw(
		_(
			"Cannot parse shortened Plus Code without a nearby geographic reference. "
			"Enter a Full Plus Code or add a clear reference and confirm location on the map."
		),
		title=_("Short Plus Code Needs Reference"),
	)


def resolve_location_reference(
	plus_code=None,
	latitude=None,
	longitude=None,
	geolocation=None,
	location_input_method=None,
	address_reference=None,
):
	"""
	Resolve a location reference to canonical {latitude, longitude, plus_code, location_source}.

	Accepts explicit coordinates, a map pin (GeoJSON), or a Plus Code.

	Returns:
		dict: {'latitude', 'longitude', 'plus_code', 'location_source'}
	"""
	latitude = float(latitude) if latitude not in (None, "") else None
	longitude = float(longitude) if longitude not in (None, "") else None

	map_latitude, map_longitude = extract_coordinates_from_geolocation(geolocation)

	if map_latitude is not None and map_longitude is not None and location_input_method == "Map Pin":
		latitude, longitude = map_latitude, map_longitude

	resolved_plus_code = normalize_plus_code(plus_code)
	location_source = location_input_method or "Coordinates"

	if resolved_plus_code:
		plus_code_result = _resolve_plus_code(
			resolved_plus_code,
			reference_latitude=latitude or map_latitude,
			reference_longitude=longitude or map_longitude,
			address_reference=address_reference,
		)
		latitude = plus_code_result["latitude"]
		longitude = plus_code_result["longitude"]
		resolved_plus_code = plus_code_result["plus_code"]
		location_source = plus_code_result["location_source"]

	if latitude is None or longitude is None:
		if map_latitude is not None and map_longitude is not None:
			latitude, longitude = map_latitude, map_longitude
			location_source = "Map Pin"
		else:
			frappe.throw(
				_("Specify coordinates, choose a point on the map, or enter a valid Plus Code."),
				title=_("Location Required"),
			)

	if not resolved_plus_code:
		resolved_plus_code = encode_plus_code(latitude, longitude)

	return {
		"latitude": round(float(latitude), 8),
		"longitude": round(float(longitude), 8),
		"plus_code": resolved_plus_code,
		"location_source": location_source,
	}
