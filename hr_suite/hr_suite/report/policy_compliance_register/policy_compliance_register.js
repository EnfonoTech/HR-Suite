// Copyright (c) 2026, Enfono Technologies and contributors
// For license information, please see LICENSE

frappe.query_reports["Policy Compliance Register"] = {
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
			fieldname: "policy_status",
			label: __("Policy Status"),
			fieldtype: "Select",
			options: "\nDraft\nActive\nUnder Review\nArchived",
		},
		{
			fieldname: "policy_category",
			label: __("Policy Category"),
			fieldtype: "Select",
			options: "\nEmployment\nAttendance\nLeave\nCompensation\nConduct\nInvestigation\nGrievance\nSafety\nOther",
		},
	],
};
