// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["WPS Submission Tracker"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			// Raw values: compared server-side to the stored English value.
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nDraft\nSubmitted\nRejected\nCorrective Action Required\nResubmitted\nAccepted\nCancelled",
		},
		{
			fieldname: "responsible_user",
			label: __("Responsible User"),
			fieldtype: "Link",
			options: "User",
		},
	],
};
