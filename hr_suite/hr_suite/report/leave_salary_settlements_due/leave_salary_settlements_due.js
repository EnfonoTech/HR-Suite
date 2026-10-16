frappe.query_reports["Leave Salary Settlements Due"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "within_days", label: __("Leave Starting Within (Days)"), fieldtype: "Int", default: 45 },
	],
};
