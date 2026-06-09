import frappe
from frappe.model.document import Document

from hr_suite.hr_suite.location_utils import build_geolocation, resolve_location_reference


class AttendanceLocation(Document):
	def validate(self):
		resolved = resolve_location_reference(
			plus_code=self.plus_code,
			latitude=self.latitude,
			longitude=self.longitude,
			geolocation=self.geolocation,
			location_input_method=self.location_input_method,
			address_reference=self.address_reference,
		)
		self.latitude = resolved["latitude"]
		self.longitude = resolved["longitude"]
		self.plus_code = resolved["plus_code"]
		self.location_source = resolved["location_source"]
		self.geolocation = build_geolocation(self.latitude, self.longitude, self.allowed_radius_meters)

	def on_update(self):
		if self.latitude and self.longitude:
			self.geolocation = build_geolocation(self.latitude, self.longitude, self.allowed_radius_meters)
			frappe.db.set_value(
				"Attendance Location",
				self.name,
				{
					"geolocation": self.geolocation,
					"plus_code": self.plus_code,
					"location_source": self.location_source,
				},
			)

	@frappe.whitelist()
	def set_geolocation(self):
		self.geolocation = build_geolocation(self.latitude, self.longitude, self.allowed_radius_meters)
		return self.geolocation

	@frappe.whitelist()
	def resolve_reference(self):
		resolved = resolve_location_reference(
			plus_code=self.plus_code,
			latitude=self.latitude,
			longitude=self.longitude,
			geolocation=self.geolocation,
			location_input_method=self.location_input_method,
			address_reference=self.address_reference,
		)
		self.update(resolved)
		self.geolocation = build_geolocation(self.latitude, self.longitude, self.allowed_radius_meters)
		return {
			**resolved,
			"geolocation": self.geolocation,
		}
