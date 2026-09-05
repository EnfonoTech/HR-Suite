// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Compliance Case Tracker"] = {
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
			// Raw values: compared server-side to the stored English value.
			fieldname: "status",
			label: __("Absence Status"),
			fieldtype: "Select",
			options: "\nOpen\nNotice Sent\nEmployee Responded\nEscalated\nClosed",
		},
		{
			fieldname: "absence_type",
			label: __("Absence Type"),
			fieldtype: "Select",
			options: "\nUnauthorised Absence\nNo Call No Show\nRepeated Late Attendance\nPartial Absence\nOther",
		},
		{
			fieldname: "from_date",
			label: __("Absent From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Absent To"),
			fieldtype: "Date",
		},
	],
};
