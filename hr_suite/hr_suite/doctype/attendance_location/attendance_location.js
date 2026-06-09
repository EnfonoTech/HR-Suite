frappe.ui.form.on("Attendance Location", {
	location_input_method: function (frm) {
		frm.trigger("resolve_reference");
	},
	plus_code: function (frm) {
		frm.trigger("resolve_reference");
	},
	address_reference: function (frm) {
		if ((frm.doc.plus_code || "").includes("+")) {
			frm.trigger("resolve_reference");
		}
	},
	latitude: function (frm) {
		frm.trigger("refresh_geolocation");
	},
	longitude: function (frm) {
		frm.trigger("refresh_geolocation");
	},
	geolocation: frappe.utils.debounce(function (frm) {
		if (frm.doc.geolocation) {
			frm.trigger("resolve_reference");
		}
	}, 800),
	allowed_radius_meters: function (frm) {
		frm.trigger("refresh_geolocation");
	},
	resolve_reference: frappe.utils.debounce(function (frm) {
		if (!frm.doc.plus_code && !frm.doc.geolocation) {
			return;
		}

		frm.call("resolve_reference").then((r) => {
			if (!r.message) return;
			frm.set_value("latitude", r.message.latitude);
			frm.set_value("longitude", r.message.longitude);
			frm.set_value("plus_code", r.message.plus_code || "");
			frm.set_value("location_source", r.message.location_source || "");
			frm.set_value("geolocation", r.message.geolocation || "");
			frm.refresh_field("geolocation");
		});
	}, 800),
	refresh_geolocation: frappe.utils.debounce(function (frm) {
		if (frm.doc.latitude && frm.doc.longitude) {
			frm.call("set_geolocation").then(() => frm.refresh_field("geolocation"));
		}
	}, 800),
	refresh: function (frm) {
		frm.add_custom_button(__("Use My Current Location"), function () {
			if (!navigator.geolocation) {
				frappe.msgprint(__("Browser does not support location services."));
				return;
			}

			navigator.geolocation.getCurrentPosition(
				(position) => {
					frm.set_value("location_input_method", "Coordinates");
					frm.set_value("latitude", position.coords.latitude);
					frm.set_value("longitude", position.coords.longitude);
					frm.set_value("location_source", "Current Device Location");
					frm.trigger("refresh_geolocation");
				},
				() => frappe.msgprint(__("Could not read the device's current location.")),
				{ enableHighAccuracy: true, timeout: 10000 }
			);
		});

		if (!frm.is_new()) {
			frm.add_custom_button(__("Update Location on Map"), function () {
				frm.trigger("refresh_geolocation");
			});
		}
	},
});
