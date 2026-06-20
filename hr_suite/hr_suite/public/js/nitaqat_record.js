// HR Suite — Nitaqat Record form: Qiwa live sync

frappe.ui.form.on("Nitaqat Record", {
	refresh(frm) {
		frappe.db.get_value("Hr Suite Settings", null, "qiwa_enabled").then(r => {
			if (!r.message || !r.message.qiwa_enabled) return;

			frm.add_custom_button(__("Sync from Qiwa"), function () {
				frappe.show_progress(__("Fetching Nitaqat from Qiwa…"), 0, 100);
				frappe.call({
					method: "hr_suite.hr_suite.integrations.qiwa.get_nitaqat_status",
					args: { company: frm.doc.company },
					callback(res) {
						frappe.hide_progress();
						if (res.exc) return;
						const d = res.message || {};
						frappe.show_alert({
							message: __(`Nitaqat synced: ${d.nitaqat_color || ""} band — ${d.saudization_percentage || "?"}%`),
							indicator: _band_color(d.nitaqat_color),
						});
						frm.reload_doc();
					},
				});
			}, __("Qiwa"));

			frm.add_custom_button(__("View Sync Logs"), function () {
				frappe.set_route("List", "Government Portal Sync Log", {
					portal: "Qiwa",
					sync_type: "Nitaqat Status",
				});
			}, __("Qiwa"));
		});
	},
});

function _band_color(color) {
	if (!color) return "blue";
	const c = color.toLowerCase();
	if (c.includes("platinum")) return "green";
	if (c.includes("green")) return "green";
	if (c.includes("yellow")) return "orange";
	if (c.includes("red")) return "red";
	return "blue";
}
