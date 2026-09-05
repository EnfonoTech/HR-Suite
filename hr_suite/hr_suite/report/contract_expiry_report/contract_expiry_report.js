// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Contract Expiry Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "alert_days",
			label: __("Expiring Within (Days)"),
			fieldtype: "Int",
			default: 60,
		},
		{
			// Raw values: the selection is compared to the stored English value server-side.
			fieldname: "contract_type",
			label: __("Contract Type"),
			fieldtype: "Select",
			options: "\nLimited\nUnlimited\nPart-Time\nFreelance",
		},
		{
			fieldname: "contract_status",
			label: __("Contract Status"),
			fieldtype: "Select",
			options: "All\nDraft\nActive\nExpired\nTerminated",
			default: "Active",
		},
	],
};
