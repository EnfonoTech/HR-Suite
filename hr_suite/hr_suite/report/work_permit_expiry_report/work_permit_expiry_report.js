// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Work Permit Expiry Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			get_query() {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
		{
			fieldname: "alert_days",
			label: __("Expiring Within (Days)"),
			fieldtype: "Int",
			default: 90,
		},
	],
};
