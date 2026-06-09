frappe.query_reports["Labor Inspection Tracker"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "inspection_authority",
			label: __("Authority"),
			fieldtype: "Select",
			options: "\nMinistry of Human Resources",
		},
		{
			fieldname: "inspection_status",
			label: __("Inspection Status"),
			fieldtype: "Select",
			options: "\nDraft",
		},
		{
			fieldname: "violation_status",
			label: __("Violation Status"),
			fieldtype: "Select",
			options: "\nOpen",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};